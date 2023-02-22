import datetime
import decimal
from decimal import Decimal, ROUND_HALF_UP
import logging
from typing import List, Tuple

import pytz
import requests

from requests import Response

from telegram import Update, ParseMode, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext

from bobweb.bob import command_service
from bobweb.bob.activities.command_activity import CommandActivity
from bobweb.bob.activities.activity_state import ActivityState
from bobweb.bob.command import ChatCommand, regex_simple_command
from bobweb.bob.resources.bob_constants import fitz, FINNISH_DATE_FORMAT

from bobweb.bob.utils_common import has, fitzstr_from, fitz_from, flatten
from bobweb.bob.utils_format import manipulate_matrix, ManipulationOperation, MessageArrayFormatter

logger = logging.getLogger(__name__)


class VatMultiplierPeriod:
    def __init__(self, start: datetime.date, end: datetime.date, vat_multiplier: Decimal):
        self.start = start
        self.end = end
        self.vat_multiplier = vat_multiplier


# Prices are in unit of EUR/MWh. So to get more conventional snt/kwh they are multiplied with 0.1
price_conversion_multiplier = Decimal('0.1')
vat_multiplier_default = 1.24
vat_multiplier_special_periods = [
    # From 1.12.2022 to 30.3.2023 VAT is temporarily lowered to 10 %
    VatMultiplierPeriod(start=datetime.date(2022, 12, 1), end=datetime.date(2023, 4, 30), vat_multiplier=Decimal('1.1'))
]

decimal_max_scale = 2  # max 2 decimals
price_max_number_count = 3  # max 3 numbers in price. So [123, 12.2, 1.23, 0.12] snt / kwh

# Note: Nordpool times are in CET (UTC+1)
nordpool_date_format = '%d-%m-%Y'
nordpool_api_endpoint = 'http://www.nordpoolspot.com/api/marketdata/page/35?currency=,,EUR,EUR'
fetch_failed_msg = 'Sähkön hintojen haku epäonnistui 🔌✂️'


class SahkoCommand(ChatCommand):
    run_async = True  # Should be asynchronous
    cache: List['DayData'] = []

    def __init__(self):
        super().__init__(
            name='sahko',
            regex=regex_simple_command('s[aä]hk[oö]'),
            help_text_short=('!sahko', 'Sähkön hinta')
        )

    def is_enabled_in(self, chat):
        return True

    def handle_update(self, update: Update, context: CallbackContext = None):
        activity = CommandActivity(initial_update=update, state=SahkoBaseState())
        command_service.instance.add_activity(activity)


# Buttons for SahkoBaseState
show_graph_btn = InlineKeyboardButton(text='Näytä graafi', callback_data='/show_graph')
hide_graph_btn = InlineKeyboardButton(text='Piilota graafi', callback_data='/hide_graph')


class SahkoBaseState(ActivityState):
    def execute_state(self, show_graph: bool = False, target_date: datetime.date = None):
        target_date = target_date or self.activity.initial_update.effective_message.date.date()
        # try:
        data: DayData = get_data_for_date(target_date=target_date)
        # except Exception as e:
        #     # Napit kanssa pois
        #     self.activity.reply_or_update_host_message(fetch_failed_msg)
        #
        #     return
        description = f'Hinnat yksikössä snt/kWh (sis. ALV {get_vat_str(get_vat_by_date(target_date))}%)'

        if show_graph:
            reply_text = f'{data.data_array}{data.data_graph}{description}'
            reply_markup = InlineKeyboardMarkup([[hide_graph_btn]])
        else:
            reply_text = f'{data.data_array}{description}'
            reply_markup = InlineKeyboardMarkup([[show_graph_btn]])

        self.activity.reply_or_update_host_message(reply_text, reply_markup, parse_mode=ParseMode.HTML)

    def handle_response(self, response_data: str, context: CallbackContext = None):
        if response_data == show_graph_btn.callback_data:
            self.execute_state(show_graph=True)
        elif response_data == hide_graph_btn.callback_data:
            self.execute_state(show_graph=False)



def get_data_for_date(target_date: datetime.date) -> 'DayData':
    cleanup_cache()
    # First try to find data from the cache
    target_date_data = next((x for x in SahkoCommand.cache if x.date == target_date), None)
    if has(target_date_data):
        return target_date_data
    return fetch_and_create_day_data(target_date)


def fetch_and_create_day_data(target_date: datetime.date) -> 'DayData':
    price_data: List[HourPriceData] = fetch_7_day_price_data()
    data_array_str, data_graph_str = get_data_array_and_graph_str(price_data, target_date)
    # Add data to cache
    target_date_data = DayData(target_date, data_array_str, data_graph_str)
    SahkoCommand.cache.append(target_date_data)
    return target_date_data


def cleanup_cache():
    SahkoCommand.cache = [x for x in SahkoCommand.cache if x.date >= datetime.date.today()]


def get_data_array_and_graph_str(price_data: List['HourPriceData'], target_date: datetime.date) -> Tuple[str, str]:
    dt_fitz = datetime.datetime.now(tz=fitz)
    past_7_day_data = [x for x in price_data if x.starting_dt.date() <= target_date]
    todays_data = [x for x in price_data if x.starting_dt.date() == target_date]

    current_hour: HourPriceData = next((x for x in todays_data
                                        if x.starting_dt.hour == dt_fitz.hour), None)

    prices_all_week = [Decimal(x.price) for x in past_7_day_data]
    _7_day_avg: Decimal = sum(prices_all_week) / len(prices_all_week)

    todays_prices = [Decimal(x.price) for x in todays_data]
    today_avg: Decimal = sum(todays_prices) / len(todays_prices)
    min_hour: HourPriceData = min(todays_data)
    max_hour: HourPriceData = max(todays_data)

    data_array = [
        ['Pörssisähkö', '', 'alkava'],
        [fitzstr_from(dt_fitz), 'hinta', 'tunti'],
        ['hinta nyt', format_price(current_hour.price), pad_int(current_hour.starting_dt.hour, pad_char='0')],
        ['alin', format_price(min_hour.price), pad_int(min_hour.starting_dt.hour, pad_char='0')],
        ['ylin', format_price(max_hour.price), pad_int(max_hour.starting_dt.hour, pad_char='0')],
        ['ka tänään', format_price(today_avg), '-'],
        ['ka 7 pv', format_price(_7_day_avg), '-'],
    ]
    formatter = MessageArrayFormatter(' ', '*')
    formatted_array = formatter.format(data_array, 1)

    todays_data_str = f'<pre>{formatted_array}</pre>'
    todays_data_graph = f'<pre>\n{create_graph(todays_data)}</pre>\n'
    return todays_data_str, todays_data_graph


# List of box chars from empty to full. Has empty + 8 levels so each character
# index in the list is equal to the number of eights it has.
# The empty being in the index 0 (/8) and full being in index 8 (/8)
box_chars_from_empty_to_full = ['░', '▁', '▂', '▃', '▄', '▅', '▆', '▇', '█']
box_char_full_block = '█'


def round_to_eight(decimal: Decimal) -> Decimal:
    """ Rounds given decimals value so that its value after decimal point is rounded to a precision of eight
        example: 1.1 => 1.0, 1.34 => 1.375, 1.49 => 1.5 and so forth """
    return Decimal((decimal * 8).to_integral_value(ROUND_HALF_UP) / 8)


def get_box_character_by_decimal_number_value(decimal: Decimal, full_bars: int, single_char_delta: Decimal):
    """ Returns box character by decimal number value (decimal number => value after decimal point)
        first rounds the value to the precision of 1/8, then returns corresponding character
        NOTE1! Empty box (single space) is returned for any negative value
        NOTE2! Emtpy string is returned for any value that's decimal value part is 0 """
    if decimal <= 0:
        return box_chars_from_empty_to_full[0]  # Zero => empty character
    if decimal == decimal.__floor__():
        return ''  # If decimal is an integer => empty string
    decimal_number_value = decimal - (full_bars * single_char_delta)
    adjusted = decimal_number_value / single_char_delta
    eights = int(round_to_eight(adjusted) / Decimal('0.125'))
    return box_chars_from_empty_to_full[eights]


def create_graph(data: List['HourPriceData']) -> str:
    graph_height_in_chars = 10
    graph_width_in_chars = 24
    graph_scaling_single_frequency = 5
    price_labels_every_n_rows = 2
    min_value = 0
    max_value: Decimal = Decimal(max(data).price / graph_scaling_single_frequency).to_integral_value(
        decimal.ROUND_CEILING) * graph_scaling_single_frequency
    single_char_delta = max_value / graph_height_in_chars
    empty_margin = 2 * ' '

    data.sort(key=lambda h: h.starting_dt)

    graph_content = get_bar_graph_content_matrix(data, min_value, graph_height_in_chars, single_char_delta)

    result_graph_str = empty_margin + create_graph_heading(data)
    for i in range(graph_height_in_chars):
        if i % price_labels_every_n_rows == 0:
            value = max_value - (i * single_char_delta)
            result_graph_str += pad_int(int(value))
        else:
            result_graph_str += empty_margin

        result_graph_str += ''.join(flatten(graph_content[i])) + '\n'

    hour_markings_bar = empty_margin + '0' + (graph_width_in_chars - 3) * '▔' + '23'
    result_graph_str += hour_markings_bar
    return result_graph_str


def create_graph_heading(data: List['HourPriceData']) -> str:
    date_str = data[0].starting_dt.strftime(FINNISH_DATE_FORMAT)
    time_range_str = f'{data[0].starting_dt.strftime("%H:%M")} - ' \
                     f'{data[-1].starting_dt.replace(minute=59).strftime("%H:%M")}'
    return f'{date_str}, {time_range_str}\n'


def get_bar_graph_content_matrix(data: List['HourPriceData'],
                                 min_value: int,
                                 graph_height: int,
                                 single_char_delta: Decimal) -> List[List]:
    horizontal_bars = []
    for hour in data:
        adjusted_price = max(hour.price, Decimal(min_value))

        full_char_count = Decimal(round_to_eight(adjusted_price / single_char_delta)).to_integral_value(
            decimal.ROUND_FLOOR)
        full_chars = int(full_char_count) * box_char_full_block

        last_char = get_box_character_by_decimal_number_value(adjusted_price, full_char_count, single_char_delta)
        empty_chars = (graph_height - len(full_chars) - len(last_char)) * box_chars_from_empty_to_full[0]
        horizontal_bars.append(full_chars + last_char + empty_chars)
    return manipulate_matrix(horizontal_bars, ManipulationOperation.ROTATE_NEG_90)


def fetch_7_day_price_data() -> List['HourPriceData']:
    """
        Nordpool data response contains 7 to 8 days of data
        Schema:
            - Rows: Hour of the day In CET (Central European Time Zone, +1)
                - Columns: Date of the hour
                    - Name: date in format '%d-%m-%Y'
                    - value: price in unit Eur / Mwh
    """
    res: Response = requests.get(nordpool_api_endpoint)
    if res.status_code != 200:
        raise ConnectionError(f'Nordpool Api error. Request got res with status: {str(res.status_code)}')
    content: dict = res.json()

    data: dict = content.get('data')

    price_data_list: List[HourPriceData] = []
    rows: List[dict] = data.get('Rows')[0:24]  # Contains some extra data, so only first 24 items are included
    for hour_index, row in enumerate(rows):
        date_data_per_hour: List[dict] = row.get('Columns')
        for datapoint in date_data_per_hour:
            # 1. extract datetime and convert it from CET to Finnish time zone datetime
            date: datetime.date = datetime.datetime.strptime(datapoint['Name'], nordpool_date_format)
            dt_in_cet_ct = datetime.datetime.combine(date, datetime.time(hour=hour_index), tzinfo=pytz.timezone('CET'))
            dt_in_fi_tz = fitz_from(dt_in_cet_ct)

            # 2. get price, convert to cent(€)/kwh, multiply by tax on target date
            price_str: str = datapoint.get('Value').replace(',', '.')
            price: Decimal = Decimal(price_str) * get_vat_by_date(dt_in_fi_tz.date()) * price_conversion_multiplier

            price_data_list.append(HourPriceData(starting_dt=dt_in_fi_tz, price=price))

    return price_data_list


class DayData:
    """ Singe dates data """
    def __init__(self, date: datetime.date, data_array: str, data_graph: str):
        self.date: datetime.date = date
        self.data_array: str = data_array
        self.data_graph: str = data_graph


class HourPriceData:
    def __init__(self, starting_dt: datetime.datetime, price: Decimal):
        """
        Single data point for electricity price. Contains price for single hour.
        :param starting_dt: datetime of starting datetime of the hour price data. NOTE! In _Finnish timezone_
        :param price: cent/kwh (€) electricity price for the hour
        """
        self.starting_dt: datetime.datetime = starting_dt
        self.price: Decimal = price

    def __lt__(self, other):
        return self.price < other.price


def get_vat_by_date(date: datetime.date):
    for period in vat_multiplier_special_periods:
        if period.start <= date <= period.end:
            return period.vat_multiplier
    return vat_multiplier_default


def get_vat_str(vat_multiplier: float) -> str:
    """ 1.24 => 24 """
    return str(round((vat_multiplier - 1) * 100))


def format_price(price: Decimal) -> str:
    """ returns formatted price str. Rounds and sets precision.
        123.123 => '123', 12.123 => '12.3', 1.123 => '1.23', 0.123 => '0.12' """
    digits_before_separator_char = len(str(price).split('.')[0])
    return str(price.quantize(Decimal('1.' + (price_max_number_count - digits_before_separator_char) * '0')))


def pad_int(number: int, min_length: int = 2, pad_char: str = ' '):
    """ If numbers str presentation is shorter than min length,
    leading chars are added (padding) to match min length """
    return (min_length - len(str(number))) * pad_char + str(number)

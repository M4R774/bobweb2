import datetime
from decimal import Decimal, ROUND_HALF_UP
import logging
from typing import List

import pytz
import requests

from requests import Response

from telegram import Update, ParseMode
from telegram.ext import CallbackContext

from bobweb.bob.command import ChatCommand, regex_simple_command

from bobweb.bob.utils_common import has, fitzstr_from, fitz_from, flatten
from bobweb.bob.utils_format import manipulate_matrix, ManipulationOperation

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

    def __init__(self):
        super().__init__(
            name='sahko',
            regex=regex_simple_command('s[aä]hk[oö]'),
            help_text_short=('!sahko', 'Sähkön hinta')
        )
        # TODO: Cache data between requests
        self.dataset = None

    def is_enabled_in(self, chat):
        return True

    def handle_update(self, update: Update, context: CallbackContext = None):
        # try:
        price_data: List[HourPriceData] = fetch_7_day_price_data()
        # except Exception as e:
        #     update.effective_chat.send_message(fetch_failed_msg)
        #     return

        todays_data = [x for x in price_data if x.starting_dt.date() == update.effective_message.date.date()]
        if len(todays_data) > 0:
            message_dt_hour_in_fitz = fitz_from(update.effective_message.date).hour
            price_now: Decimal = next((x.price for x in todays_data
                                       if x.starting_dt.hour == message_dt_hour_in_fitz), None)
            price_now_row = f'hinta nyt: {format_price(price_now)} snt/kWh\n' if has(price_now) else ''

            prices = [Decimal(x.price) for x in todays_data]
            avg: Decimal = sum(prices) / len(prices)
            min_hour: HourPriceData = min(todays_data)
            max_hour: HourPriceData = max(todays_data)
            vat_str = get_vat_str(get_vat_by_date(update.effective_message.date.date()))
            todays_data_str = f'Pörssisähkö {fitzstr_from(update.effective_message.date)} ⚡ ' \
                              f'(sis. ALV {vat_str}%)\n' \
                              f'{price_now_row}' \
                              f'keski: {format_price(avg)} snt/kWh\n' \
                              f'alin: {format_price(min_hour.price)} snt/kWh, klo {min_hour.hour_range_str()}, \n' \
                              f'ylin: {format_price(max_hour.price)} snt/kWh, klo {max_hour.hour_range_str()}'

            graph = create_graph(todays_data)

            todays_data_str += f'\n<pre>\n' \
                               f'{graph}\n' \
                               f'</pre>'
        else:
            todays_data_str = 'Ei onnaa'

        update.effective_chat.send_message(todays_data_str, parse_mode=ParseMode.HTML)


# List of box chars from empty to full. Has empty + 8 levels so each character
# index in the list is equal to the number of eights it has.
# The empty being in the index 0 (/8) and full being in index 8 (/8)
box_chars_from_empty_to_full = ['░', '▁', '▂', '▃', '▄', '▅', '▆', '▇', '█']
box_char_full_block = '█'


def round_to_eight(decimal: Decimal) -> Decimal:
    """ Rounds given decimals value so that its value after decimal point is rounded to a precision of eight
        example: 1.1 => 1.0, 1.34 => 1.375, 1.49 => 1.5 and so forth """
    return Decimal((decimal * 8).to_integral_value(ROUND_HALF_UP) / 8)


def get_box_character_by_decimal_number_value(decimal: Decimal):
    """ Returns box character by decimal number value (decimal number => value after decimal point)
        first rounds the value to the precision of 1/8, then returns corresponding character
        NOTE! Empty box (single space) is returned for any negative value
        NOTE2! Emtpy string is returned for any value that's decimal value part is 0 """
    if decimal <= 0:
        return box_chars_from_empty_to_full[0]  # Zero => emtpy character
    if decimal == decimal.__floor__():
        return ''  # If decimal is a integer => empty string
    decimal_number_value = decimal - decimal.__floor__()  # value after decimal dot
    eights = int(round_to_eight(decimal_number_value) / Decimal('0.125'))
    return box_chars_from_empty_to_full[eights]


def create_graph(data: List['HourPriceData']) -> str:
    # Alkuun yksinkertainen tilanne, missä
    # 28 merkkiä on maksimi, joista menee
    # 24 merkkiä tunneille ja
    # 2 merkkiä hinnalle
    # 2 merkkiä taulukon laidoille
    # esimerkkirivi:
    # 10|      ▅▄▃▂▁
    # ...
    #  0|███████████████████████
    #   ╚═══════════════════════
    #    0    6  9 12 15 18 21
    graph_height_in_chars = 10
    graph_width_in_chars = 24
    price_labels_every_n_rows = 2
    time_labels_every_n_cols = 3
    displayed_hours = len(data)
    min_value = 0
    max_value = 10
    single_char_delta: Decimal = Decimal(max_value) / Decimal(graph_height_in_chars)

    prices_labels = []
    for i in range(graph_height_in_chars):
        if i % 2 == 0:
            prices_labels.append(i)
    prices_labels.sort(reverse=True)

    data.sort(key=lambda h: h.starting_dt)

    graph_content = get_bar_graph_content_matrix(data, min_value, max_value)

    result_graph_str = ''
    for i in range(graph_height_in_chars):
        if i % price_labels_every_n_rows == 0:
            value = graph_height_in_chars - (i * single_char_delta)
            result_graph_str += get_padded_int(int(value))
        else:
            result_graph_str += 2 * ' '

        result_graph_str += ''.join(flatten(graph_content[i])) + '\n'

    result_graph_str += ' ' * 2
    for i in range(graph_width_in_chars):
        if i % time_labels_every_n_cols == 0:
            result_graph_str += str(i) + (time_labels_every_n_cols - len(str(i))) * '░'

    print(result_graph_str)
    return result_graph_str


def get_bar_graph_content_matrix(data: List['HourPriceData'], min_value: int, max_value: int) -> List[List]:
    horizontal_bars = []
    for hour in data:
        adjusted_price = max(min(hour.price, Decimal(max_value)), Decimal(min_value))
        bar = int(adjusted_price) * box_char_full_block + get_box_character_by_decimal_number_value(adjusted_price)
        bar += Decimal(max_value - adjusted_price).__floor__() * box_chars_from_empty_to_full[0]
        horizontal_bars.append(bar)
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
            # 1. extract datetime and convert it to finnish time zone datetime
            date: datetime.date = datetime.datetime.strptime(datapoint['Name'], nordpool_date_format)
            dt_in_cet_ct = datetime.datetime.combine(date, datetime.time(hour=hour_index), tzinfo=pytz.timezone('CET'))
            dt_in_fi_tz = fitz_from(dt_in_cet_ct)

            # 2. get price, convert to cent(€)/kwh, multiply by tax on target date
            price_str: str = datapoint.get('Value').replace(',', '.')
            price: Decimal = Decimal(price_str) * get_vat_by_date(dt_in_fi_tz.date()) * price_conversion_multiplier

            price_data_list.append(HourPriceData(starting_dt=dt_in_fi_tz, price=price))

    return price_data_list


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

    def hour_range_str(self):
        return f'{get_padded_int(self.starting_dt.hour, pad_char="0")}:00 - ' \
               f'{get_padded_int(self.starting_dt.hour, pad_char="0")}:59'


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


def get_padded_int(number: int, min_length: int = 2, pad_char: str = ' '):
    """ If numbers str presentation is shorter than min length,
    leading chars are added (padding) to match min length """
    return (min_length - len(str(number))) * pad_char + str(number)

from datetime import datetime

import datetime
import decimal
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Union

import pytz
import requests

from requests import Response

from bobweb.bob.resources.bob_constants import fitz, FINNISH_DATE_FORMAT

from bobweb.bob.utils_common import has, fitzstr_from, fitz_from, flatten, min_max_normalize
from bobweb.bob.utils_format import manipulate_matrix, ManipulationOperation, MessageArrayFormatter


class NordpoolCache:
    cache: List['DayData'] = []
    next_day_fetch_try_count = 0


def find_cached_data_for_date(target_date: datetime.date) -> Union['DayData', None]:
    return next((x for x in NordpoolCache.cache if x.date == target_date), None)


def cache_has_data_for_tomorrow():
    tomorrow = datetime.datetime.now(tz=fitz).date() + datetime.timedelta(days=1)
    return find_cached_data_for_date(tomorrow) is not None


class VatMultiplierPeriod:
    def __init__(self, start: datetime.date, end: datetime.date, vat_multiplier: Decimal):
        self.start = start
        self.end = end
        self.vat_multiplier = vat_multiplier


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


def cleanup_cache():
    """ Cleans up old data from the cache. If cache is empty or only contains relevant data, does nothing """
    NordpoolCache.cache = [x for x in NordpoolCache.cache if x.date >= datetime.date.today()]
    NordpoolCache.next_day_fetch_try_count = 0


def get_data_for_date(target_date: datetime.date) -> DayData | None:
    """ First check if new data should be fetched to the cache. If so, do fetch and process.
        Then return data for target date (or None if none) """
    data = find_cached_data_for_date(target_date)
    if data is None and should_update_cache():
        fetch_and_create_day_data_to_cache()
        data = find_cached_data_for_date(target_date)

    return data


def should_update_cache():
    """ Should update cache if it's empty, or it if it has not been updated after expected next day data release """
    is_empty = len(NordpoolCache.cache) == 0

    time_now = datetime.datetime.now(tz=fitz).time()
    next_day_data_should_be_available = time_now >= next_day_data_release_time
    try_limit_not_reached = NordpoolCache.next_day_fetch_try_count < next_day_data_fetch_try_count_limit

    return is_empty or (next_day_data_should_be_available and try_limit_not_reached)


def fetch_and_create_day_data_to_cache() -> None:
    # 1. Fetch available data from nordpool api
    price_data: List[HourPriceData] = fetch_and_process_price_data_from_nordpool_api()
    # 2. Process data for today and tomorrow if available
    for i in range(2):
        date = datetime.datetime.now(tz=fitz).date() + (i * datetime.timedelta(days=1))
        day_data: DayData | None = create_day_data_for_date(price_data, date)

        if has(day_data):
            NordpoolCache.cache.append(day_data)


def create_day_data_for_date(price_data: List[HourPriceData], target_date: datetime.date) -> DayData | None:
    target_date_data = extract_target_date(price_data, target_date)
    if len(target_date_data) < expected_count_of_datapoints_after_tz_shift:
        return None

    target_days_prices = [Decimal(x.price) for x in target_date_data]
    target_date_avg: Decimal = sum(target_days_prices) / len(target_days_prices)
    min_hour: HourPriceData = min(target_date_data)
    max_hour: HourPriceData = max(target_date_data)

    past_7_day_data = extract_target_day_and_prev_6_days(price_data, target_date)
    prices_all_week = [Decimal(x.price) for x in past_7_day_data]
    _7_day_avg: Decimal = sum(prices_all_week) / len(prices_all_week)

    target_date_str = fitzstr_from(datetime.datetime.combine(date=target_date, time=datetime.time()))
    target_date_desc = 'tänään' if target_date == datetime.datetime.now(tz=fitz).date() else 'huomenna'

    data_array = [
        ['Pörssisähkö', '', 'alkava'],
        [target_date_str, 'hinta', 'tunti'],
        ['alin', format_price(min_hour.price), pad_int(min_hour.starting_dt.hour, pad_char='0')],
        ['ylin', format_price(max_hour.price), pad_int(max_hour.starting_dt.hour, pad_char='0')],
        [f'ka {target_date_desc}', format_price(target_date_avg), '-'],
        ['ka 7 pv', format_price(_7_day_avg), '-'],
    ]

    current_hour_data: HourPriceData = extract_current_hour_data_or_none(target_date_data)
    if current_hour_data is not None:
        price_now_row = ['hinta nyt', format_price(current_hour_data.price), pad_int(current_hour_data.starting_dt.hour, pad_char='0')]
        data_array.insert(2, price_now_row)

    formatter = MessageArrayFormatter(' ', '*')
    formatted_array = formatter.format(data_array, 1)

    data_str = f'<pre>{formatted_array}</pre>'
    data_graph = f'<pre>\n{create_graph(target_date_data)}</pre>\n'
    return DayData(target_date, data_str, data_graph)


def extract_target_date(price_data: List[HourPriceData], target_date: datetime.date) -> List[HourPriceData]:
    return [x for x in price_data if x.starting_dt.date() == target_date]


def extract_target_day_and_prev_6_days(price_data: List[HourPriceData], target_date: datetime.date) -> List[HourPriceData]:
    date_range_start: datetime.date = target_date - datetime.timedelta(days=6)
    return [x for x in price_data if date_range_start <= x.starting_dt.date() <= target_date]


def extract_current_hour_data_or_none(data: List[HourPriceData]):
    now = datetime.datetime.now(tz=fitz)
    generator = (x for x in data if x.starting_dt.date() == now.date() and x.starting_dt.hour == now.hour)
    return next(generator, None)


# List of box chars from empty to full. Has empty + 8 levels so each character
# index in the list is equal to the number of eights it has.
# The empty being in the index 0 (/8) and full being in index 8 (/8)
box_chars_from_empty_to_full = ['░', '▁', '▂', '▃', '▄', '▅', '▆', '▇', '█']
box_char_full_block = '█'


def round_to_eight(decimal: Decimal) -> Decimal:
    """ Rounds given decimals decimal part value so that it is rounded to a precision of eight
        example: 1.1 => 1.0, 1.34 => 1.375, 1.49 => 1.5 and so forth """
    return Decimal((decimal * 8).to_integral_value(ROUND_HALF_UP) / 8)


def get_box_character_by_decimal_part_value(decimal: Decimal) -> str:
    """
    Returns box character by decimal part value (decimal number => value after decimal point)
        first rounds the value to the precision of 1/8, then returns corresponding character
        NOTE1! Empty box (single space) is returned for any negative value
        NOTE2! Empty string is returned for any value that's decimal value part is 0
    :param decimal: value
    :return: str - single char for the decimal number part of the given value
    """
    if decimal <= 0:
        return box_chars_from_empty_to_full[0]  # Zero => empty character
    if decimal == decimal.__floor__():
        return ''  # If decimal is an integer => empty string
    decimal_part = decimal - decimal.__floor__()
    eights = int(round_to_eight(decimal_part) / Decimal('0.125'))
    return box_chars_from_empty_to_full[eights]


def create_graph(data: List[HourPriceData]) -> str:
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


def create_graph_heading(data: List[HourPriceData]) -> str:
    date_str = data[0].starting_dt.strftime(FINNISH_DATE_FORMAT)
    time_range_str = f'{data[0].starting_dt.strftime("%H:%M")} - ' \
                     f'{data[-1].starting_dt.replace(minute=59).strftime("%H:%M")}'
    return f'{date_str}, {time_range_str}\n'


def get_bar_graph_content_matrix(data: List[HourPriceData],
                                 min_value: int,
                                 graph_height: int,
                                 single_char_delta: Decimal) -> List[List]:
    old_min = min_value
    old_max = old_min + graph_height * single_char_delta
    new_min = old_min
    new_max = graph_height

    horizontal_bars = []
    for hour in data:
        # Adjust price to decimal number of full bars displayed using min-max normalization.
        scaled_value = min_max_normalize(hour.price, old_min, old_max, new_min, new_max)

        full_char_count = scaled_value.to_integral_value(decimal.ROUND_FLOOR)
        full_chars = int(full_char_count) * box_char_full_block

        last_char = get_box_character_by_decimal_part_value(scaled_value)

        empty_chars = (graph_height - len(full_chars) - len(last_char)) * box_chars_from_empty_to_full[0]
        horizontal_bars.append(full_chars + last_char + empty_chars)
    return manipulate_matrix(horizontal_bars, ManipulationOperation.ROTATE_NEG_90)


def get_vat_by_date(date: datetime.date):
    for period in vat_multiplier_special_periods:
        if period.start <= date <= period.end:
            return period.vat_multiplier
    return vat_multiplier_default


def get_vat_str(vat_multiplier: float | Decimal) -> str:
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


# Prices are in unit of EUR/MWh. So to get more conventional snt/kwh they are multiplied with 0.1
price_conversion_multiplier = Decimal('0.1')
vat_multiplier_default = Decimal('1.24')
vat_multiplier_special_periods = [
    # From 1.12.2022 to 30.3.2023 VAT is temporarily lowered to 10 %
    VatMultiplierPeriod(start=datetime.date(2022, 12, 1), end=datetime.date(2023, 4, 30), vat_multiplier=Decimal('1.1'))
]

# Expected time in UTC+2 (Finnish time zone) when next days data is expected to be released
next_day_data_release_time = datetime.time(hour=13, minute=45)
# If next days data is not available, fetch is tried again maximum of n times
next_day_data_fetch_try_count_limit = 5

expected_count_of_datapoints_after_tz_shift = 23

decimal_max_scale = 2  # max 2 decimals
price_max_number_count = 3  # max 3 numbers in price. So [123, 12.2, 1.23, 0.12] snt / kwh

# Note: Nordpool times are in CET (UTC+1)
nordpool_date_format = '%d-%m-%Y'
nordpool_api_endpoint = 'https://www.nordpoolgroup.com/api/marketdata/page/35?currency=,,EUR,EUR'


def fetch_and_process_price_data_from_nordpool_api() -> List['HourPriceData']:
    """
        Nordpool data response contains 7 to 8 days of data.
        From 13:15 UTC+2 till 23:59 UTC+2 the response contains next days data as well (8 days).
        Outside that the response contains current day and past six days of data (7 days).
        NOTE! As the data is in UTC+1, timezone shift is used to localize all values to correct local times
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



from datetime import datetime

import datetime
import decimal
from decimal import Decimal, ROUND_HALF_UP
from typing import List

import pytz

from bobweb.bob import async_http
from bobweb.bob.resources.bob_constants import fitz, FINNISH_DATE_FORMAT

from bobweb.bob.utils_common import has, fitzstr_from, fitz_from, flatten, min_max_normalize
from bobweb.bob.utils_format import manipulate_matrix, ManipulationOperation, MessageArrayFormatter


class NordpoolCache:
    cache: List['HourPriceData'] = []
    next_day_fetch_try_count = 0


def cache_has_data_for_date(target_date: datetime.date) -> bool:
    data_for_date = [x for x in NordpoolCache.cache if x.starting_dt.date() == target_date]
    return len(data_for_date) >= expected_count_of_datapoints_after_tz_shift


def cache_has_data_for_tomorrow():
    tomorrow = datetime.datetime.now(tz=fitz).date() + datetime.timedelta(days=1)
    return cache_has_data_for_date(tomorrow)


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


class PriceDataNotFoundForDate(Exception):
    """ Exception for situation where price data is not found for given date even after nordpool api call """
    pass


def cleanup_cache():
    """ Clears cache if it does not contain all data for current date """
    today = datetime.datetime.now(tz=fitz).date()
    todays_data = [x for x in NordpoolCache.cache if x.starting_dt.date() == today]
    if len(todays_data) < 24:
        NordpoolCache.next_day_fetch_try_count = 0
        NordpoolCache.cache = []


async def get_data_for_date(target_date: datetime.date, graph_width: int = None) -> DayData:
    """
        First check if new data should be fetched to the cache. If so, do fetch and process.
        Then return data for target date.
        NOTE! Raises PriceDataNotFoundForDate exception if data is not found for the date
    :param target_date: date for which DayData is requested
    :param graph_width: preferred graph width. Global default is used if None
    :return: DayData object or raises exception
    """
    if cache_has_data_for_date(target_date) is False:
        await fetch_process_and_cache_data()

    return create_day_data_for_date(NordpoolCache.cache, target_date, graph_width)


async def fetch_process_and_cache_data() -> List[HourPriceData]:
    # 1. Fetch and process available data from nordpool api
    price_data: List[HourPriceData] = await fetch_and_process_price_data_from_nordpool_api()
    # 2. Add the latest data to the cache
    NordpoolCache.cache = price_data
    return price_data


def create_day_data_for_date(price_data: List[HourPriceData], target_date: datetime.date, graph_width: int) -> DayData:
    target_date_data = extract_target_date(price_data, target_date)

    if len(target_date_data) < expected_count_of_datapoints_after_tz_shift:
        raise PriceDataNotFoundForDate(f"No price data found for date: {target_date}")

    target_days_prices = [Decimal(x.price) for x in target_date_data]
    target_date_avg: Decimal = Decimal(sum(target_days_prices)) / Decimal(len(target_days_prices))
    min_hour: HourPriceData = min(target_date_data)
    max_hour: HourPriceData = max(target_date_data)

    past_7_day_data = extract_target_day_and_prev_6_days(price_data, target_date)
    prices_all_week = [Decimal(x.price) for x in past_7_day_data]
    _7_day_avg: Decimal = Decimal(sum(prices_all_week)) / Decimal(len(prices_all_week))

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
        price_now_row = ['hinta nyt', format_price(current_hour_data.price),
                         pad_int(current_hour_data.starting_dt.hour, pad_char='0')]
        data_array.insert(2, price_now_row)

    formatter = MessageArrayFormatter(' ', '*')
    formatted_array = formatter.format(data_array, 1)

    data_str = f'<pre>{formatted_array}</pre>'
    data_graph = f'<pre>\n{create_graph(target_date_data, graph_width)}</pre>\n'
    return DayData(target_date, data_str, data_graph)


def extract_target_date(price_data: List[HourPriceData], target_date: datetime.date) -> List[HourPriceData]:
    return [x for x in price_data if x.starting_dt.date() == target_date]


def extract_target_day_and_prev_6_days(price_data: List[HourPriceData],
                                       target_date: datetime.date) -> List[HourPriceData]:
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
default_graph_width = 24


def round_to_eight(d: Decimal) -> Decimal:
    """ Rounds given decimals decimal part value so that it is rounded to a precision of eight
        example: 1.1 => 1.0, 1.34 => 1.375, 1.49 => 1.5 and so forth """
    return Decimal((d * 8).to_integral_value(ROUND_HALF_UP) / 8)


def get_box_character_by_decimal_part_value(d: Decimal) -> str:
    """
    Returns box character by decimal part value (decimal number => value after decimal point)
        first rounds the value to the precision of 1/8, then returns corresponding character
        NOTE1! Empty box (single space) is returned for any negative value
        NOTE2! Empty string is returned for any value that's decimal value part is 0
    :param d: value
    :return: str - single char for the decimal number part of the given value
    """
    if d <= 0:
        return box_chars_from_empty_to_full[0]  # Zero => empty character
    if d == d.__floor__():
        return ''  # If decimal is an integer => empty string
    decimal_part = get_decimal_part(d)
    eights = int(round_to_eight(decimal_part) / Decimal('0.125'))
    return box_chars_from_empty_to_full[eights]


def create_graph(data: List[HourPriceData], graph_width: int) -> str:
    graph_height_in_chars = 10
    graph_width = min((graph_width or default_graph_width), default_graph_width)  # None safe smaller of two

    graph_scaling_single_frequency = 5
    price_labels_every_n_rows = 2
    min_value = 0
    max_value: Decimal = Decimal(max(data).price / graph_scaling_single_frequency).to_integral_value(
        decimal.ROUND_CEILING) * graph_scaling_single_frequency
    single_char_delta = max_value / graph_height_in_chars
    empty_margin = 2 * ' '

    data.sort(key=lambda h: h.starting_dt)

    interpolated_data = get_interpolated_data_points(data, graph_width)

    graph_content = get_bar_graph_content_matrix(interpolated_data, min_value, graph_height_in_chars, single_char_delta)

    result_graph_str = empty_margin + create_graph_heading(data)
    for i in range(graph_height_in_chars):
        if i % price_labels_every_n_rows == 0:
            value = max_value - (i * single_char_delta)
            result_graph_str += pad_int(int(value))
        else:
            result_graph_str += empty_margin

        result_graph_str += ''.join(flatten(graph_content[i])) + '\n'

    result_graph_str += get_hour_marking_bar(empty_margin, graph_width)
    return result_graph_str


def get_hour_marking_bar(empty_margin: str, graph_width: int) -> str:
    """ Returns hour marking based of the width of the graph. Only displays first and last hour start (0 & 23) as
        There is no knowledge of a number character set that would render with the same width as the box characters
        on both mobile and pc telegram clients while using monospace parsing. Normal number would drift the left as
        they as slightly narrower as the box characters"""
    last_hour_str = '23' if graph_width > 3 else ''
    return empty_margin + '0' + (graph_width - 3 + 2 - len(last_hour_str)) * '▔' + last_hour_str


def create_graph_heading(data: List[HourPriceData]) -> str:
    date_str = data[0].starting_dt.strftime(FINNISH_DATE_FORMAT)
    time_range_str = f'{data[0].starting_dt.strftime("%H:%M")} - ' \
                     f'{data[-1].starting_dt.replace(minute=59).strftime("%H:%M")}'
    return f'{date_str}, {time_range_str}\n'


def get_interpolated_data_points(data: List[HourPriceData], graph_width: int):
    """
    Interpolates value range data points to more compress list if graph is requested in smaller size.
    Basic logic of this interpolation:
    - calculate how many hours each segment contains
    - iterate from 0 to graph width. In each iteration calculate weighted average for the price
        - weighted average is calculated by sum of each hour price included in the range multiplied with ratio in
          which it's included in the range
    - add that weighted average as the new data point for that segment
    :param data: List of HourPriceData data points
    :param graph_width: count of data points to which data is interpolated.
        Graph width => number of value segments => number of box characters on screen
    :return:
    """
    if len(data) == graph_width:
        return [x.price for x in data]

    single_char_time_delta_hours = Decimal(len(data) / graph_width)  # 24 hours in a day

    interpolated_data = []
    for segment_index in range(graph_width):
        segment_start = segment_index * single_char_time_delta_hours
        segment_end = segment_index * single_char_time_delta_hours + single_char_time_delta_hours
        # Make sure that rounding error won't cause index error later on
        segment_end = min(segment_end, len(data))

        weighted_sum_of_range_prices = get_weighted_sum_of_time_range_prices(data, segment_start, segment_end)
        weighted_average_price = weighted_sum_of_range_prices / (segment_end - segment_start)
        interpolated_data.append(weighted_average_price)
    return interpolated_data


def get_weighted_sum_of_time_range_prices(data: List[HourPriceData],
                                          segment_start: Decimal,
                                          segment_end: Decimal) -> Decimal:
    total: Decimal = Decimal(0)
    for hour_index in range(segment_start.__floor__(), segment_end.__ceil__()):
        hour_price = data[hour_index].price

        if hour_index < segment_start:  # First hour is not whole and has decimal part
            hour_weight = 1 - get_decimal_part(segment_start)
        elif segment_end.__floor__() == hour_index and segment_end - hour_index != 0:  # Last hour is not whole and has decimal part
            hour_weight = get_decimal_part(segment_end)
        else:
            hour_weight = 1

        total += hour_price * hour_weight
    return total


def get_bar_graph_content_matrix(prices: List[Decimal],
                                 min_value: int,
                                 graph_height: int,
                                 single_char_delta: Decimal) -> List[List]:
    old_min = min_value
    old_max = old_min + graph_height * single_char_delta
    new_min = old_min
    new_max = graph_height

    horizontal_bars = []
    for price in prices:
        # Adjust price to decimal number of full bars displayed using min-max normalization.
        scaled_value = min_max_normalize(price, old_min, old_max, new_min, new_max)

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


def get_decimal_part(d: Decimal):
    return d - d.__floor__()


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


async def fetch_and_process_price_data_from_nordpool_api() -> List['HourPriceData']:
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
    content: dict = await async_http.fetch_json(nordpool_api_endpoint)
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

            # For some reason, there might be missing data which is represented with single dash character
            if price_str == '-':
                price_str = '0'

            price: Decimal = Decimal(price_str) * get_vat_by_date(dt_in_fi_tz.date()) * price_conversion_multiplier

            price_data_list.append(HourPriceData(starting_dt=dt_in_fi_tz, price=price))

    return price_data_list

import datetime
import decimal
import statistics
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Optional

import pytz
import xmltodict
from telegram.constants import ParseMode
from telegram.ext import CallbackContext

from bobweb.bob import async_http, config
from bobweb.bob.message_board import MessageWithPreview
from bobweb.bob.resources.bob_constants import fitz, FINNISH_DATE_FORMAT
from bobweb.bob.utils_common import fitzstr_from, fitz_from, flatten, min_max_normalize, object_search
from bobweb.bob.utils_format import manipulate_matrix, ManipulationOperation, MessageArrayFormatter

# Expected time, when next days price data should be available. In UTC time.
NEXT_DAY_DATA_EXPECTED_RELEASE = datetime.time().replace(hour=10, minute=45)


class NordpoolCache:
    cache: List['HourPriceData'] = []


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


def _get_vat_str(vat_multiplier: float | Decimal) -> str:
    """ 1.255 => 25.5 """
    as_percentage = (vat_multiplier - 1) * 100
    if as_percentage == round(as_percentage):
        return str(round(as_percentage))
    else:
        return "{:.1f}".format((vat_multiplier - 1) * 100)


class DayData:
    """ Singe dates electricity price data """

    def __init__(self,
                 date: datetime.date,
                 data_array: str,
                 data_graph: str,
                 min_price: Decimal = None,
                 max_price: Decimal = None,
                 avg_price: Decimal = None,
                 # If this dates values were calculated with partial missing data
                 price_data_missing_this_date: bool = False,
                 price_data_missing_6_prev_dates: bool = False):
        self.date: datetime.date = date
        self.data_array: str = data_array
        self.data_graph: str = data_graph
        self.min_price = min_price
        self.max_price = max_price
        self.avg_price = avg_price
        self.price_data_missing_this_date = price_data_missing_this_date
        self.price_data_missing_6_prev_dates = price_data_missing_6_prev_dates

    def _get_price_description(self):
        return f'Hinnat yksikössä snt/kWh (sis. ALV {_get_vat_str(get_vat_by_date(self.date))}%)'

    def _get_missing_data_description(self):
        common_missing_template = ('Hintatietoja puuttuu {} päivän ajalta. Huomioi, '
                                   'että annetut tiedot ovat suuntaa antavia.')
        if self.price_data_missing_this_date and self.price_data_missing_6_prev_dates:
            return common_missing_template.format('valitun päivän ja sitä edeltävän 6') + '\n'
        elif self.price_data_missing_this_date:
            return common_missing_template.format('valitun') + '\n'
        elif self.price_data_missing_6_prev_dates:
            return common_missing_template.format('edeltävän 6') + '\n'
        else:
            return ''

    def create_message(self, show_graph: bool = False):
        return (f'{self.data_array}'
                f'{self.data_graph if show_graph else ""}'
                f'{self._get_missing_data_description()}'
                f'{self._get_price_description()}')

    async def create_message_board_message(self) -> MessageWithPreview:
        preview = (f'⚡️ {self.date.strftime("%d.%m.")} '
                   f'📉 {format_price(self.min_price)}'
                   f'📈 {format_price(self.max_price)}'
                   f'📊 {format_price(self.avg_price)}')
        body = self.create_message(show_graph=False)
        return MessageWithPreview(preview=preview, body=body, parse_mode=ParseMode.HTML)


class HourPriceData:
    def __init__(self, starting_dt: datetime, price: Optional[Decimal]):
        """
        Single data point for electricity price. Contains price for single hour.
        :param starting_dt: datetime of starting datetime of the hour price data. NOTE! In _Finnish timezone_
        :param price: cent/kwh (€) electricity price for the hour or None if missing data
        """
        self.starting_dt: datetime.datetime = starting_dt
        # Note! Price can be none if there is no price data for the hour
        self.price: Optional[Decimal] = price

    def __lt__(self, other):
        return self.price < other.price


class PriceDataNotFoundForDate(Exception):
    """ Exception for situation where price data is not found for given date even after entsoe api call """
    pass


async def cleanup_cache(context: CallbackContext = None):
    """ Clears cache if it does not contain all data for current date.
        Async function so that it can be called by PTB scheduler. Context for the scheduler. """
    today = datetime.datetime.now(tz=fitz).date()
    todays_data = [x for x in NordpoolCache.cache if x.starting_dt.date() == today]
    if len(todays_data) < 24:
        NordpoolCache.cache = []


async def get_data_for_date(target_date: datetime.date, graph_width: int = None) -> DayData:
    """
        First check if new data should be fetched to the cache. If so, do fetch and process.
        Then return data for target date.
        New data should be fetched if there is no data for current date OR it's past 13:15

        NOTE! Raises PriceDataNotFoundForDate exception if data is not found for the date
    :param target_date: date for which DayData is requested
    :param graph_width: preferred graph width. Global default is used if None
    :return: DayData object or raises exception
    """
    cache_has_no_data_for_target_date = cache_has_data_for_date(target_date) is False
    cache_has_no_data_for_tomorrow_and_it_should_be_released = \
        (cache_has_data_for_tomorrow() is False
         and datetime.datetime.now(tz=pytz.utc).time() > NEXT_DAY_DATA_EXPECTED_RELEASE)

    if cache_has_no_data_for_target_date or cache_has_no_data_for_tomorrow_and_it_should_be_released:
        await fetch_process_and_cache_data()

    return create_day_data_for_date(NordpoolCache.cache, target_date, graph_width)


async def fetch_process_and_cache_data() -> List[HourPriceData]:
    # 1. Fetch and process available data from entsoe api
    price_data: List[HourPriceData] = await fetch_and_process_price_data_from_entsoe_api()
    # 2. Add the latest data to the cache
    NordpoolCache.cache = price_data
    return price_data


def create_day_data_for_date(price_data: List[HourPriceData], target_date: datetime.date, graph_width: int) -> DayData:
    all_data_for_target_date = extract_target_date(price_data, target_date)

    if len(all_data_for_target_date) < expected_count_of_datapoints_after_tz_shift:
        raise PriceDataNotFoundForDate(f"No price data found for date: {target_date}")

    # Check that there is no missing price data
    target_date_missing_prices = [x for x in all_data_for_target_date if x.price is None]
    target_dates_data = [x for x in all_data_for_target_date if x.price is not None]

    target_dates_prices: List[Decimal] = [Decimal(x.price) for x in target_dates_data]
    target_date_avg: Decimal = Decimal(sum(target_dates_prices)) / Decimal(len(target_dates_prices))
    min_hour: HourPriceData = min(target_dates_data)
    max_hour: HourPriceData = max(target_dates_data)

    previous_6_day_data = extract_prev_6_days(price_data, target_date)
    past_6_days_missing_prices = [x for x in previous_6_day_data if x.price is None]
    if past_6_days_missing_prices:
        previous_6_day_data = [x for x in previous_6_day_data if x.price is not None]

    past_7_day_prices: List[Decimal] = target_dates_prices + [Decimal(x.price) for x in previous_6_day_data]
    past_7_days_average: Decimal = Decimal(statistics.mean(past_7_day_prices))

    target_date_str = fitzstr_from(datetime.datetime.combine(date=target_date, time=datetime.time()))
    is_today = target_date == datetime.datetime.now(tz=fitz).date()
    target_date_desc = ('tänään' if is_today else 'huomenna') + ('*' if target_date_missing_prices else '')

    past_7_day_desc = 'ka 7 pv' + ('*' if past_6_days_missing_prices else '')

    data_array = [
        ['Pörssisähkö', '', 'alkava'],
        [target_date_str, 'hinta', 'tunti'],
        ['alin', format_price(min_hour.price), pad_int(min_hour.starting_dt.hour, pad_char='0')],
        ['ylin', format_price(max_hour.price), pad_int(max_hour.starting_dt.hour, pad_char='0')],
        [f'ka {target_date_desc}', format_price(target_date_avg), '!!' if target_date_missing_prices else '-'],
        [past_7_day_desc, format_price(past_7_days_average), '!!' if past_6_days_missing_prices else '-'],
    ]

    if is_today:
        current_hour_data: HourPriceData = extract_current_hour_data_or_none(all_data_for_target_date)
        if current_hour_data:
            price_now_row = ['hinta nyt',
                             format_price(current_hour_data.price) if current_hour_data.price else '-',
                             pad_int(current_hour_data.starting_dt.hour, pad_char='0')]
            data_array.insert(2, price_now_row)

    formatter = MessageArrayFormatter(' ', '*')
    formatted_array = formatter.format(data_array, 1)
    data_str = f'<pre>{formatted_array}</pre>'

    graph_string = create_graph(target_dates_data, graph_width)
    data_graph = f'<pre>\n{graph_string}</pre>\n'

    return DayData(target_date, data_str, data_graph,
                   min_hour.price, max_hour.price, target_date_avg,
                   target_date_missing_prices, past_6_days_missing_prices)


def extract_target_date(price_data: List[HourPriceData], target_date: datetime.date) -> List[HourPriceData]:
    return [x for x in price_data if x.starting_dt.date() == target_date]


def extract_prev_6_days(price_data: List[HourPriceData],
                        target_date: datetime.date) -> List[HourPriceData]:
    date_range_start: datetime.date = target_date - datetime.timedelta(days=6)
    date_range_end: datetime.date = target_date - datetime.timedelta(days=1)
    return [x for x in price_data if date_range_start <= x.starting_dt.date() <= date_range_end]


def extract_current_hour_data_or_none(data: List[HourPriceData]) -> HourPriceData | None:
    now = datetime.datetime.now(tz=fitz)
    generator = (x for x in data if x.starting_dt.date() == now.date() and x.starting_dt.hour == now.hour)
    return next(generator, None)


# List of box chars from empty to full. Has empty + 8 levels so each character
# index in the list is equal to the number of eights it has.
# The empty being in the index 0 (/8) and full being in index 8 (/8)
box_chars_from_empty_to_full = ['░', '▁', '▂', '▃', '▄', '▅', '▆', '▇', '█']
box_char_full_block = '█'
default_graph_width = 24
default_graph_height = 10


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
    graph_width = min((graph_width or default_graph_width), default_graph_width)  # None-safe smaller of two
    graph_scaling_frequency = 5
    price_labels_every_n_rows = 2
    # With box characters there is no way to display negative values, so 0 is the minimum value for the graph
    min_value = 0
    max_value: Decimal = (Decimal(max(data).price / graph_scaling_frequency)
                          .to_integral_value(decimal.ROUND_CEILING) * graph_scaling_frequency)
    single_char_delta = max_value / default_graph_height
    empty_margin = 2 * ' '

    data.sort(key=lambda h: h.starting_dt)

    interpolated_data: List[Decimal] = get_interpolated_data_points(data, graph_width)

    graph_content = get_bar_graph_content_matrix(interpolated_data, min_value, single_char_delta)

    result_graph_str = empty_margin + create_graph_heading(data)
    for i in range(default_graph_height):
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


def get_interpolated_data_points(data: List[HourPriceData], graph_width: int) -> List[Decimal]:
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
    data_point_count = len(data)
    if data_point_count == graph_width:
        return [x.price for x in data]

    single_char_time_delta_hours: Decimal = Decimal(data_point_count / graph_width)  # 24 hours in a day

    interpolated_data = []
    for segment_index in range(graph_width):
        segment_start = segment_index * single_char_time_delta_hours
        segment_end = segment_index * single_char_time_delta_hours + single_char_time_delta_hours
        # Make sure that rounding error won't cause index error later on
        segment_end = min(segment_end, Decimal(data_point_count))

        weighted_sum_of_range_prices: Decimal = get_weighted_sum_of_time_range_prices(data, segment_start, segment_end)
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


def get_bar_graph_content_matrix(prices: List[Decimal], min_value: int, single_char_delta: Decimal) -> List[str]:
    old_max = min_value + default_graph_height * single_char_delta

    horizontal_bars = []
    for price in prices:
        # Adjust price to decimal number of full bars displayed using min-max normalization.
        try:
            scaled_value = min_max_normalize(price, min_value, old_max, min_value, default_graph_height)
        except decimal.DivisionUndefined | decimal.DivisionByZero:
            scaled_value = 0

        full_char_count = scaled_value.to_integral_value(decimal.ROUND_FLOOR)
        full_chars = int(full_char_count) * box_char_full_block

        last_char = get_box_character_by_decimal_part_value(scaled_value)

        empty_chars = (default_graph_height - len(full_chars) - len(last_char)) * box_chars_from_empty_to_full[0]
        horizontal_bars.append(full_chars + last_char + empty_chars)
    return manipulate_matrix(horizontal_bars, ManipulationOperation.ROTATE_NEG_90)


def get_vat_by_date(date: datetime.date):
    for period in vat_multiplier_special_periods:
        if period.start <= date <= period.end:
            return period.vat_multiplier
    return vat_multiplier_default


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
vat_multiplier_default = Decimal('1.255')

# Special vat periods. Old data left as the tests contain prices calculated with 10 % vat.
vat_multiplier_special_periods = [
    # From 1.12.2022 to 30.3.2023 VAT is temporarily lowered to 10 %
    VatMultiplierPeriod(start=datetime.date(2022, 12, 1), end=datetime.date(2023, 4, 30), vat_multiplier=Decimal('1.1')),
    # From 1.4.2024 to 31.8.2024 VAT was 24 %
    VatMultiplierPeriod(start=datetime.date(2022, 4, 1), end=datetime.date(2024, 8, 31), vat_multiplier=Decimal('1.24'))
]

# Expected time in UTC+2 (Finnish time zone) when next days data is expected to be released
next_day_data_release_time = datetime.time(hour=13, minute=45)
# If next days data is not available, fetch is tried again maximum of n times
next_day_data_fetch_try_count_limit = 5

expected_count_of_datapoints_after_tz_shift = 23

decimal_max_scale = 2  # max 2 decimals
price_max_number_count = 3  # max 3 numbers in price. So [123, 12.2, 1.23, 0.12] snt / kwh

# Note: Entso-e times are in CET (UTC+1)
entsoe_date_format = '%Y-%m-%dT%H:%M%z'
entsoe_api_endpoint = 'https://web-api.tp.entsoe.eu/api'


async def fetch_and_process_price_data_from_entsoe_api() -> List['HourPriceData']:
    """
        Entso-e data response contains 7 to 8 days of data.
        From 13:15 UTC+2 till 23:59 UTC+2 the response contains next days data as well (8 days).
        Outside that the response contains current day and past six days of data (7 days).

        Entso-E API documentation can be found from:
        - Postman doc: https://documenter.getpostman.com/view/7009892/2s93JtP3F6#3b383df0-ada2-49fe-9a50-98b1bb201c6b
        - API integration guide: https://transparencyplatform.zendesk.com/hc/en-us/sections/12783116987028-Restful-API-integration-guide
        - Old Restful API-guide: https://transparency.entsoe.eu/content/static_content/Static%20content/web%20api/Guide.html#_parameters

        Note! Time is returned in UTC+-0.
    """
    period_start = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=7)
    period_end = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=1)

    # Different eic-codes can be found: https://www.entsoe.eu/data/energy-identification-codes-eic/eic-area-codes-map/
    finland_bidding_zone_eic_code = '10YFI-1--------U'
    request_dt_pattern = '%Y%m%d%H%M'
    params: dict = {
        'securityToken': config.entsoe_api_key,                      # [Required] API key
        'documentType': 'A44',                                       # [Required] API doc description: "Price Document". Seems to be identifier for this price-request (Day Ahead Prices)
        'periodStart': period_start.strftime(request_dt_pattern),    # [Required] Pattern yyyyMMddHHmm
        'periodEnd': period_end.strftime(request_dt_pattern),        # [Required] Pattern yyyyMMddHHmm
        'out_Domain': finland_bidding_zone_eic_code,                 # [Required] EIC code of a Bidding Zone
        'in_Domain': finland_bidding_zone_eic_code,                  # [Required] EIC code of a Bidding Zone (must be same as out_Domain)
        'contract_MarketAgreement.type': 'A01'                       # [Optional] A01 = Day-ahead ; A07 = Intraday
    }
    xml_content_str: str = await async_http.get_content_text(entsoe_api_endpoint, params=params)
    content_dict: dict = xmltodict.parse(xml_content_str)
    return parse_price_data(content_dict)


def parse_price_data(content: dict) -> List['HourPriceData']:
    price_data_list: List[HourPriceData] = []

    daily_data: List[dict] = object_search(content, 'Publication_MarketDocument', 'TimeSeries') or []

    for i, day_data in enumerate(daily_data):
        time_interval_start_str = object_search(day_data, 'Period', 'timeInterval', 'start')
        time_interval_start: datetime.datetime = datetime.datetime.strptime(time_interval_start_str, entsoe_date_format)

        hourly_data: list = object_search(day_data, 'Period', 'Point') or []
        for datapoint in hourly_data:
            # 1. extract datetime and convert it from CET to Finnish time zone datetime
            hour_index = int(datapoint.get('position'))
            dt_in_utc = time_interval_start + datetime.timedelta(hours=hour_index - 1)
            dt_in_fi_tz = fitz_from(dt_in_utc)

            # 2. get price, convert to cent(€)/kwh, if positive, multiply by tax on target date.
            price_str: str = datapoint.get('price.amount')
            price_decimal: Optional[Decimal] = parse_decimal_or_none(price_str)

            if price_decimal is not None:
                price_in_cents_per_kwh: Decimal = price_decimal * price_conversion_multiplier

                if price_in_cents_per_kwh > 0:
                    # VAT is only included if the price is positive
                    price_in_cents_per_kwh *= get_vat_by_date(dt_in_fi_tz.date())
                data_for_hour = HourPriceData(starting_dt=dt_in_fi_tz, price=price_in_cents_per_kwh)
            else:
                data_for_hour = HourPriceData(starting_dt=dt_in_fi_tz, price=None)

            price_data_list.append(data_for_hour)
    # return sort by starting time
    return sorted(price_data_list, key=lambda item: item.starting_dt)


def parse_decimal_or_none(input_string: str) -> Optional[Decimal]:
    try:
        return Decimal(input_string)
    except Exception:
        return None

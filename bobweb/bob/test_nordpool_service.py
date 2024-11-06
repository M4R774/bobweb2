import datetime
from decimal import Decimal
from typing import List

from unittest import mock

import django
import pytest
import xmltodict
from django.test import TestCase
from unittest.mock import Mock

from freezegun import freeze_time
from freezegun.api import FrozenDateTimeFactory

from bobweb.bob import main, nordpool_service

from bobweb.bob.nordpool_service import NordpoolCache, round_to_eight, \
    get_box_character_by_decimal_part_value, format_price, DayData, get_data_for_date, HourPriceData, \
    get_hour_marking_bar, get_interpolated_data_points
from bobweb.bob.utils_format import manipulate_matrix, ManipulationOperation


expected_data_point_count = 8 * 24 + 21  # => 8 full days and some more => 213 data points in the test set

async def mock_response_200_with_test_data(*args, **kwargs) -> str:
    with open('bobweb/bob/resources/test/entsoe_mock_data.xml', mode='r', encoding='utf-8') as file:
        """ Real data returned from the API to be used for testing. Search-query (security-token omitted):
            https://web-api.tp.entsoe.eu/api?documentType=A44&out_Domain=10YFI-1--------U&in_Domain=10YFI-1--------U&periodStart=202302092300&periodEnd=202302172300
            So contains data for time period 2023-02-09 - 2023-02-17 """
        return file.read()


def get_mock_day_data(price_data: List[HourPriceData], target_date: datetime.date, graph_width) -> DayData | None:
    return DayData(date=target_date, data_graph=f'graph_{target_date}', data_array=f'array_{target_date}')


# Define frozen time that is included in the mock data set. Mock data contains data for 10.-17.2.2023
@pytest.mark.asyncio
@freeze_time(datetime.datetime(2023, 2, 17))
# By default, if nothing else is defined, all request.get requests are returned with this mock
@mock.patch('bobweb.bob.async_http.get_content_text', mock_response_200_with_test_data)
class NorpoolServiceTests(django.test.TransactionTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super(NorpoolServiceTests, cls).setUpClass()
        cls.maxDiff = None

    async def test_fetch_and_process_price_data_from_entsoe_api(self):
        """ Tests that fetching and processing data from entso-e api works as expected. Uses test data response to
            mocked get-request. """
        nordpool_service.parse_price_data(xmltodict.parse(await mock_response_200_with_test_data()))


    @mock.patch('bobweb.bob.nordpool_service.create_day_data_for_date', side_effect=get_mock_day_data)
    async def test_that_data_is_cached(self, mock_fetch: Mock):
        NordpoolCache.cache = []
        self.assertEqual(0, len(NordpoolCache.cache))

        today = datetime.date.today()
        # Call twice in the row. Length of the cache should not change on consecutive calls
        # Mock data has data for current and the next date, so the cache starts with length of 2
        await get_data_for_date(today)
        self.assertEqual(expected_data_point_count, len(NordpoolCache.cache))

        await get_data_for_date(today)
        self.assertEqual(expected_data_point_count, len(NordpoolCache.cache))

        # Now mock should have been called only once as after the first call the values have been already cached
        self.assertEqual(2, mock_fetch.call_count)

    @freeze_time(datetime.datetime(2023, 2, 16), as_arg=True)
    async def test_when_cleanup_cache_old_data_is_removed(clock: FrozenDateTimeFactory, self):
        await self.test_that_data_is_cached()  # Call prev test
        self.assertEqual(expected_data_point_count, len(NordpoolCache.cache))

        # When date has not changed then cleanup_cache should not clear cached data
        await nordpool_service.cleanup_cache()
        self.assertEqual(expected_data_point_count, len(NordpoolCache.cache))

        clock.tick(datetime.timedelta(days=1))
        # When date is changed cleanup_cache should empty cache, if current date is not contained in it
        # As the data had 8 days of data, current date is still included, so nothing is removed
        await nordpool_service.cleanup_cache()
        self.assertEqual(expected_data_point_count, len(NordpoolCache.cache))

        clock.tick(datetime.timedelta(days=1))
        # Now after second tick current date is no longer in the cached data, so it is cleared
        await nordpool_service.cleanup_cache()
        self.assertEqual(0, len(NordpoolCache.cache))

    async def test_hour_price_data_interpolation(self):
        def hour_price_data(hour: int, price: int | float):
            return HourPriceData(datetime.datetime(year=2023, month=5, day=3, hour=hour, minute=0), Decimal(price))

        # Each price_data represents spot price for whole hour starting at given hour
        data = [
            hour_price_data(0, 2),
            hour_price_data(1, 4),
            hour_price_data(2, 6),
            hour_price_data(3, 8),
            hour_price_data(4, 10),
            hour_price_data(5, 12),
        ]
        # Now when we interpolate this data to 5 data points, each segment / new data point represents 1.2 hours of
        # data. This means, that weighted average is calculated based on each original hour segment overlapping new
        # segment. For example:
        # 1. new segment: from 00:00 -> 01:29 (1,5 hours), weighted average: (1 * 2 + 0.5 * 4) / 1.5 == 3
        # 1. new segment: from 01:30 -> 02:59 (1,5 hours), weighted average: (0.5 * 2 + 1 * 6) / 1.5 == 7
        expected_interpolated_data = ['3.00', '7.00', '11.00']
        actual_interpolated_data = get_interpolated_data_points(data, graph_width=3)
        actual_data_formatted = ['{0:.2f}'.format(x) for x in actual_interpolated_data]
        self.assertEqual(expected_interpolated_data, actual_data_formatted)

    async def test_price_array_to_be_as_expected(self):
        today = datetime.date.today()
        await get_data_for_date(today)

        expected_array = '<pre>' \
                         'Pörssisähkö       alkava\n' \
                         '17.02.2023  hinta  tunti\n' \
                         '************************\n' \
                         'hinta nyt    3.47     02\n' \
                         'alin         3.28     23\n' \
                         'ylin         10.8     13\n' \
                         'ka tänään    6.38      -\n' \
                         'ka 7 pv      7.34      -\n' \
                         '</pre>'
        actual_array = (await get_data_for_date(today)).data_array

        self.assertEqual(actual_array, expected_array)

    async def test_graph_to_be_as_expected(self):
        expected_array = '<pre>\n' \
                         '  17.02.2023, 00:00 - 23:59\n' \
                         '15░░░░░░░░░░░░░░░░░░░░░░░░\n' \
                         '  ░░░░░░░░░░░░░░░░░░░░░░░░\n' \
                         '12░░░░░░░░░░░░░▂░░░░░░░░░░\n' \
                         '  ░░░░░░░░▇▇▄▃▆█▅░░░░░░░░░\n' \
                         ' 9░░░░░░░▆███████▁░░░░░░░░\n' \
                         '  ░░░░░░░█████████▃▂░░░░░░\n' \
                         ' 6░░░░░░▇███████████▇░░░░░\n' \
                         '  ▄▅▃▃▃▄█████████████▇▆▄▃▁\n' \
                         ' 3████████████████████████\n' \
                         '  ████████████████████████\n' \
                         '  0▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔23</pre>\n'
        today = datetime.date.today()
        actual_array = (await get_data_for_date(today)).data_graph
        self.assertEqual(actual_array, expected_array)

    async def test_graph_with_narrower_width_is_as_expected(self):
        expected_array = '<pre>\n' \
                         '  17.02.2023, 00:00 - 23:59\n' \
                         '15░░░░░░░░░░░░\n' \
                         '  ░░░░░░░░░░░░\n' \
                         '12░░░░░░░░░░░░\n' \
                         '  ░░░░▇▄█░░░░░\n' \
                         ' 9░░░░███▇░░░░\n' \
                         '  ░░░▆████▃░░░\n' \
                         ' 6░░░██████▃░░\n' \
                         '  ▄▃▄███████▅▂\n' \
                         ' 3████████████\n' \
                         '  ████████████\n' \
                         '  0▔▔▔▔▔▔▔▔▔23</pre>\n'
        today = datetime.date.today()
        actual_array = (await get_data_for_date(today, graph_width=12)).data_graph
        self.assertEqual(actual_array, expected_array)

    async def test_hour_marking_bar(self):
        empty_margin = ' ' * 2
        self.assertEqual('  0▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔23', get_hour_marking_bar(empty_margin, 24))
        self.assertEqual('  0▔▔▔▔▔▔▔▔▔23', get_hour_marking_bar(empty_margin, 12))
        self.assertEqual('  0▔23', get_hour_marking_bar(empty_margin, 4))
        self.assertEqual('  0▔▔', get_hour_marking_bar(empty_margin, 3))
        self.assertEqual('  0▔', get_hour_marking_bar(empty_margin, 2))
        self.assertEqual('  0', get_hour_marking_bar(empty_margin, 1))

    async def test_function_round_to_eight(self):
        def expect_output_from_input(expected_output: str, decimal: str):
            self.assertEqual(Decimal(expected_output), round_to_eight(Decimal(decimal)))

        expect_output_from_input('123', '123')
        expect_output_from_input('123.0', '123.05')
        expect_output_from_input('0.125', '0.0625')  # Half should round up
        expect_output_from_input('123.125', '123.12')
        expect_output_from_input('123.25', '123.222222')

    async def test_get_box_character_by_decimal_number_value(self):
        def expect_box_char_from_decimal(char: str, decimal: str):
            actual_char = get_box_character_by_decimal_part_value(Decimal(decimal))
            self.assertEqual(char, actual_char)

        expect_box_char_from_decimal('░', '0')
        expect_box_char_from_decimal('░', '0.01')
        expect_box_char_from_decimal('▁', '0.1')
        expect_box_char_from_decimal('▂', '0.249')
        expect_box_char_from_decimal('▃', '0.375')
        expect_box_char_from_decimal('▄', '0.5')
        expect_box_char_from_decimal('▅', '0.625')
        expect_box_char_from_decimal('▆', '0.75')
        expect_box_char_from_decimal('▇', '0.825')
        expect_box_char_from_decimal('█', '0.95')
        expect_box_char_from_decimal('', '1')

        # Only decimal number (value after decimal dot) matters
        expect_box_char_from_decimal('▁', '1.124')
        # For negative values, empty box (single space) is returned
        expect_box_char_from_decimal('░', '-1.5')

    async def test_matrix_of_box_chars_is_rotated_correctly(self):
        box_char_matrix = [['█', '█', '▃'],
                           ['▆', ' ', ' '],
                           ['█', '▁', ' ']]
        rotated_matrix = manipulate_matrix(box_char_matrix, ManipulationOperation.ROTATE_NEG_90)
        expected = [['▃', ' ', ' '],
                    ['█', ' ', '▁'],
                    ['█', '▆', '█']]
        self.assertEqual(expected, rotated_matrix)

    async def test_decimal_money_amount_formatting(self):
        # Money amount is expected to be presented with scaling precision
        self.assertEqual('123', format_price(Decimal('123.456')))
        self.assertEqual('12.3', format_price(Decimal('12.345')))
        self.assertEqual('1.23', format_price(Decimal('1.234')))
        self.assertEqual('0.12', format_price(Decimal('0.123')))

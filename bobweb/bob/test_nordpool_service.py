import datetime
import json
from decimal import Decimal
from typing import List

from unittest import mock
from django.test import TestCase
from unittest.mock import Mock

import requests
from freezegun import freeze_time
from freezegun.api import FrozenDateTimeFactory
from requests import Response

from bobweb.bob import main, command_sahko, nordpool_service
from bobweb.bob.command_sahko import SahkoCommand, show_graph_btn, hide_graph_btn

from bobweb.bob.nordpool_service import NordpoolCache, nordpool_api_endpoint, round_to_eight, \
    get_box_character_by_decimal_part_value, get_vat_by_date, format_price, DayData, get_data_for_date, HourPriceData, \
    get_hour_marking_bar
from bobweb.bob.tests_mocks_v2 import init_chat_user
from bobweb.bob.tests_utils import MockResponse, assert_command_triggers, mock_response_with_code
from bobweb.bob.utils_format import manipulate_matrix, ManipulationOperation


def mock_response_200_with_test_data(url: str, *args, **kwargs):
    with open('bobweb/bob/resources/test/nordpool_mock_data.json') as example_json:
        mock_json_dict: dict = json.loads(example_json.read())
        return MockResponse(status_code=200, content=mock_json_dict)


def get_mock_day_data(price_data: List[HourPriceData], target_date: datetime.date) -> DayData | None:
    return DayData(date=target_date, data_graph=f'graph_{target_date}', data_array=f'array_{target_date}')


class NordpoolApiEndpointPingTest(TestCase):
    """ Smoke test against the real api """

    def test_epic_games_api_endpoint_ok(self):
        res: Response = requests.get(nordpool_api_endpoint)
        self.assertEqual(200, res.status_code)


# Define frozen time that is included in the mock data set
@freeze_time(datetime.datetime(2023, 2, 17))
# By default, if nothing else is defined, all request.get requests are returned with this mock
@mock.patch('requests.get', mock_response_200_with_test_data)
class NorpoolServiceTests(TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super(NorpoolServiceTests, cls).setUpClass()
        cls.maxDiff = None
        SahkoCommand.run_async = False

    @mock.patch('bobweb.bob.nordpool_service.create_day_data_for_date', side_effect=get_mock_day_data)
    def test_that_data_is_cached(self, mock_fetch: Mock):
        NordpoolCache.cache = []
        self.assertEqual(0, len(NordpoolCache.cache))

        today = datetime.date.today()
        # Call twice in the row. Length of the cache should not change on consecutive calls
        # Mock data has data for current and the next date, so the cache starts with length of 2
        get_data_for_date(today)
        self.assertEqual(2, len(NordpoolCache.cache))

        get_data_for_date(today)
        self.assertEqual(2, len(NordpoolCache.cache))

        # Now mock should have been called only once as after the first call the values have been already cached
        self.assertEqual(2, mock_fetch.call_count)

    @freeze_time(datetime.datetime(2023, 2, 17), as_kwarg='clock')
    def test_when_cleanup_cache_old_data_is_removed(self, clock: FrozenDateTimeFactory):
        self.test_that_data_is_cached()  # Call prev test
        self.assertEqual(2, len(NordpoolCache.cache))

        # When date has not changed then cleanup_cache should not clear cached data
        nordpool_service.cleanup_cache()
        self.assertEqual(2, len(NordpoolCache.cache))

        # When date is changed cleanup_cache should remove old data.
        # As cache contains data for current and the next date, each tick of day removes one days data
        clock.tick(datetime.timedelta(days=1))
        nordpool_service.cleanup_cache()
        self.assertEqual(1, len(NordpoolCache.cache))

        clock.tick(datetime.timedelta(days=1))
        nordpool_service.cleanup_cache()
        self.assertEqual(0, len(NordpoolCache.cache))

    @freeze_time(datetime.datetime(2023, 2, 17))
    def test_price_array_to_be_as_expected(self):
        today = datetime.date.today()
        get_data_for_date(today)

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
        actual_array = get_data_for_date(today).data_array

        self.assertEqual(actual_array, expected_array)

    @freeze_time(datetime.datetime(2023, 2, 17))
    def test_graph_to_be_as_expected(self):
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
        actual_array = get_data_for_date(today).data_graph
        self.assertEqual(actual_array, expected_array)

    @freeze_time(datetime.datetime(2023, 2, 17))
    def test_graph_with_narrower_width_is_as_expected(self):
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
        actual_array = get_data_for_date(today, graph_width=12).data_graph
        self.assertEqual(actual_array, expected_array)

    def test_hour_marking_bar(self):
        empty_margin = ' ' * 2
        self.assertEqual('  0▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔23', get_hour_marking_bar(empty_margin, 24))
        self.assertEqual('  0▔▔▔▔▔▔▔▔▔23', get_hour_marking_bar(empty_margin, 12))
        self.assertEqual('  0▔23', get_hour_marking_bar(empty_margin, 4))
        self.assertEqual('  0▔▔', get_hour_marking_bar(empty_margin, 3))
        self.assertEqual('  0▔', get_hour_marking_bar(empty_margin, 2))
        self.assertEqual('  0', get_hour_marking_bar(empty_margin, 1))

    def test_function_round_to_eight(self):
        def expect_output_from_input(expected_output: str, decimal: str):
            self.assertEqual(Decimal(expected_output), round_to_eight(Decimal(decimal)))

        expect_output_from_input('123', '123')
        expect_output_from_input('123.0', '123.05')
        expect_output_from_input('0.125', '0.0625')  # Half should round up
        expect_output_from_input('123.125', '123.12')
        expect_output_from_input('123.25', '123.222222')

    def test_get_box_character_by_decimal_number_value(self):
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

    def test_matrix_of_box_chars_is_rotated_correctly(self):
        box_char_matrix = [['█', '█', '▃'],
                           ['▆', ' ', ' '],
                           ['█', '▁', ' ']]
        rotated_matrix = manipulate_matrix(box_char_matrix, ManipulationOperation.ROTATE_NEG_90)
        expected = [['▃', ' ', ' '],
                    ['█', ' ', '▁'],
                    ['█', '▆', '█']]
        self.assertEqual(expected, rotated_matrix)

    def test_gives_correct_vat_multiplier_by_date(self):
        self.assertEqual(Decimal('1.24'), get_vat_by_date(datetime.date(2000, 1, 1)))
        self.assertEqual(Decimal('1.24'), get_vat_by_date(datetime.date(2022, 11, 30)))
        self.assertEqual(Decimal('1.10'), get_vat_by_date(datetime.date(2022, 12, 1)))
        self.assertEqual(Decimal('1.10'), get_vat_by_date(datetime.date(2023, 4, 30)))
        self.assertEqual(Decimal('1.24'), get_vat_by_date(datetime.date(2023, 5, 1)))

    def test_decimal_money_amount_formatting(self):
        # Money amount is expected to be presented with scaling precision
        self.assertEqual('123', format_price(Decimal('123.456')))
        self.assertEqual('12.3', format_price(Decimal('12.345')))
        self.assertEqual('1.23', format_price(Decimal('1.234')))
        self.assertEqual('0.12', format_price(Decimal('0.123')))

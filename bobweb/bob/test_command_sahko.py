import datetime
import io
import json
import os
from decimal import Decimal

from unittest import mock
from django.test import TestCase
from unittest.mock import Mock, patch

import requests
from freezegun import freeze_time
from freezegun.api import FrozenDateTimeFactory
from requests import Response

from bobweb.bob import main, command_sahko
from bobweb.bob.command_sahko import format_price, SahkoCommand, box_chars_from_empty_to_full, \
    get_box_character_by_decimal_part_value, nordpool_api_endpoint, show_graph_btn, get_vat_by_date, hide_graph_btn, \
    DayData, round_to_eight
from bobweb.bob.tests_mocks_v2 import init_chat_user
from bobweb.bob.tests_utils import MockResponse, assert_command_triggers, mock_response_with_code
from bobweb.bob.utils_format import manipulate_matrix, ManipulationOperation


class NordpoolApiEndpointPingTest(TestCase):
    """ Smoke test against the real api """
    def test_epic_games_api_endpoint_ok(self):
        res: Response = requests.get(nordpool_api_endpoint)
        self.assertEqual(200, res.status_code)


@mock.patch('requests.get', mock_response_with_code(status_code=400, content={}))
class SahkoCommandFetchOrProcessError(TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super(SahkoCommandFetchOrProcessError, cls).setUpClass()
        SahkoCommand.run_async = False

    def test_should_inform_if_fetch_failed(self):
        SahkoCommand.run_async = False
        chat, user = init_chat_user()
        user.send_message('/sahko')
        self.assertIn(command_sahko.fetch_failed_msg, chat.last_bot_txt())


def mock_response_200_with_test_data(url: str, *args, **kwargs):
    with open('bobweb/bob/resources/test/nordpool_mock_data.json') as example_json:
        mock_json_dict: dict = json.loads(example_json.read())
        return MockResponse(status_code=200, content=mock_json_dict)


# Define frozen time that is included in the mock data set
@freeze_time(datetime.datetime(2023, 2, 17))
# By default, if nothing else is defined, all request.get requests are returned with this mock
@mock.patch('requests.get', mock_response_200_with_test_data)
class SahkoCommandTests(TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super(SahkoCommandTests, cls).setUpClass()
        SahkoCommand.run_async = False

    def test_command_triggers(self):
        # Nordic characteds 'ä' and 'ö' should be interchangeable with their
        should_trigger = ['/sahko', '!sahko', '.sahko', '/SAHKO', '/sähkö', '/sahkö', '/sähko']
        should_not_trigger = ['sahko', 'test /sahko', '/sahko test']
        assert_command_triggers(self, SahkoCommand, should_trigger, should_not_trigger)

    def test_should_contain_price_now(self):
        chat, user = init_chat_user()
        user.send_message('/sahko')
        self.assertIn('hinta nyt    3.47', chat.last_bot_txt())

    def test_graph_can_be_toggled_on_and_off(self):
        chat, user = init_chat_user()
        user.send_message('/sahko')
        # First should have no grap, then after first button press graph should appear and after second disappear again
        expected_graph_slice = '9░░░░░░░▆███████▁░░░░░░░░'
        self.assertNotIn(expected_graph_slice, chat.last_bot_txt())
        user.press_button(show_graph_btn.text)
        self.assertIn(expected_graph_slice, chat.last_bot_txt())
        user.press_button(hide_graph_btn.text)
        self.assertNotIn(expected_graph_slice, chat.last_bot_txt())

    @mock.patch('bobweb.bob.command_sahko.get_data_array_and_graph_str')
    def test_that_data_is_cached(self, mock_fetch: Mock):
        mock_fetch.return_value = f'[array]\n', '[graph]\n'  # mock processed data
        SahkoCommand.cache = []
        chat, user = init_chat_user()
        self.assertEqual(0, len(SahkoCommand.cache))

        # Call twice in the row. Length of the cache should not have changed
        user.send_message('/sahko')
        self.assertEqual(1, len(SahkoCommand.cache))

        user.send_message('/sahko')
        self.assertEqual(1, len(SahkoCommand.cache))

        # Now mock should have been called only once as after the first call the values have been already cached
        self.assertEqual(1, mock_fetch.call_count)

    @freeze_time(datetime.datetime(2023, 2, 17), as_kwarg='clock')
    @mock.patch('bobweb.bob.command_sahko.get_data_array_and_graph_str')
    def test_when_cleanup_cache_old_data_is_removed(self, mock_fetch: Mock, clock: FrozenDateTimeFactory):
        self.test_that_data_is_cached()  # Call prev test
        self.assertEqual(1, len(SahkoCommand.cache))

        # When date has not changed then cleanup_cache should not clear cached data
        command_sahko.cleanup_cache()
        self.assertEqual(1, len(SahkoCommand.cache))

        # When date is changed cleanup_cache should remove old data
        clock.tick(datetime.timedelta(days=1))
        command_sahko.cleanup_cache()
        self.assertEqual(0, len(SahkoCommand.cache))

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

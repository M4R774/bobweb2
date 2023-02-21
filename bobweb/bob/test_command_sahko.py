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
from requests import Response

from bobweb.bob import main
from bobweb.bob.command_sahko import format_price, SahkoCommand, box_chars_from_empty_to_full, \
    get_box_character_by_decimal_number_value, nordpool_api_endpoint, show_graph_btn
from bobweb.bob.tests_mocks_v2 import init_chat_user
from bobweb.bob.tests_utils import MockResponse, assert_command_triggers
from bobweb.bob.utils_format import manipulate_matrix, ManipulationOperation


class NordpoolApiEndpointPingTest(TestCase):
    """ Smoke test against the real api """

    def test_epic_games_api_endpoint_ok(self):
        res: Response = requests.get(nordpool_api_endpoint)
        self.assertEqual(200, res.status_code)


def mock_response_200_with_test_data(url: str, *args, **kwargs):
    with open('bobweb/bob/resources/test/nordpool_mock_data.json') as example_json:
        mock_json_dict: dict = json.loads(example_json.read())
        return MockResponse(status_code=200, content=mock_json_dict)


# By default, if nothing else is defined, all request.get requests are returned with this mock
@mock.patch('requests.get', mock_response_200_with_test_data)
class SahkoCommandTests(TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super(SahkoCommandTests, cls).setUpClass()
        os.system("python bobweb/web/manage.py migrate")
        SahkoCommand.run_async = False

    def test_check_box_chars(self):
        print(''.join(box_chars_from_empty_to_full))

    def test_function_round_to_eight(self):
        def expect_output_from_input(expected_output: str, input: str):
            self.assertEqual(Decimal(expected_output), Decimal(input))

        expect_output_from_input('123', '123')
        expect_output_from_input('123.0', '123.05')
        expect_output_from_input('0.125', '0.0625')  # Half should round up
        expect_output_from_input('123.125', '123.12')
        expect_output_from_input('123.25', '123.222222')

    def test_get_box_character_by_decimal_number_value(self):
        def expect_box_char_from_decimal(char: str, decimal: str):
            self.assertEqual(char, get_box_character_by_decimal_number_value(Decimal(decimal)))

        expect_box_char_from_decimal(' ', '0')
        expect_box_char_from_decimal(' ', '0.01')
        expect_box_char_from_decimal('▁', '0.1')
        expect_box_char_from_decimal('▂', '0.249')
        expect_box_char_from_decimal('▃', '0.375')
        expect_box_char_from_decimal('▄', '0.5')
        expect_box_char_from_decimal('▅', '0.625')
        expect_box_char_from_decimal('▆', '0.75')
        expect_box_char_from_decimal('▇', '0.825')
        expect_box_char_from_decimal('█', '0.95')
        expect_box_char_from_decimal('█', '1')

        # Only decimal number (value after decimal dot) matters
        expect_box_char_from_decimal('▁', '1.124')
        # For negative values, empty box (single space) is returned
        expect_box_char_from_decimal(' ', '-1.5')

    def test_matrix_of_box_chars_is_rotated_correctly(self):
        box_char_matrix = [['█', '█', '▃'],
                           ['▆', ' ', ' '],
                           ['█', '▁', ' ']]
        rotated_matrix = manipulate_matrix(box_char_matrix, ManipulationOperation.ROTATE_NEG_90)
        expected = [['▃', ' ', ' '],
                    ['█', ' ', '▁'],
                    ['█', '▆', '█']]
        self.assertEqual(expected, rotated_matrix)

    def test_command_triggers(self):
        should_trigger = ['/sahko', '!sahko', '.sahko', '/SAHKO']
        should_not_trigger = ['sahko', 'test /sahko', '/sahko test']
        assert_command_triggers(self, SahkoCommand, should_trigger, should_not_trigger)

    @freeze_time(datetime.datetime(2023, 2, 17))
    def test_should_return_expected_game_name_from_mock_data(self):
        chat, user = init_chat_user()
        user.send_message('/sahko')
        self.assertIn('hinta nyt    3.47', chat.last_bot_txt())

        user.press_button(show_graph_btn.text)

    #
    # def test_should_inform_if_fetch_failed(self):
    #     with mock.patch('requests.get', mock_response_with_code(404)):
    #         chat, user = init_chat_user()
    #         user.send_message('/epicgames')
    #         self.assertIn(command_epic_games.fetch_failed_msg, chat.last_bot_txt())
    #
    # def test_should_inform_if_response_ok_but_no_free_games(self):
    #     with mock.patch('requests.get', mock_response_with_code(200, {})):
    #         chat, user = init_chat_user()
    #         user.send_message('/epicgames')
    #         self.assertIn(command_epic_games.fetch_ok_no_free_games, chat.last_bot_txt())

    def test_decimal_money_amount_formatting(self):
        # Money amount is expected to be presented with scaling precision
        self.assertEqual('123', format_price(Decimal('123.456')))
        self.assertEqual('12.3', format_price(Decimal('12.345')))
        self.assertEqual('1.23', format_price(Decimal('1.234')))
        self.assertEqual('0.12', format_price(Decimal('0.123')))

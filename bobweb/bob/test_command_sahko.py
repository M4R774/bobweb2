import datetime
import json
from decimal import Decimal

from unittest import mock
from django.test import TestCase
from unittest.mock import Mock

from freezegun import freeze_time
from freezegun.api import FrozenDateTimeFactory

from bobweb.bob import main, command_sahko
from bobweb.bob.activities.activity_state import back_button
from bobweb.bob.command_sahko import SahkoCommand, show_graph_btn, hide_graph_btn, show_tomorrow_btn, info_btn, \
    show_today_btn

from bobweb.bob.nordpool_service import NordpoolCache
from bobweb.bob.test_nordpool_service import mock_response_200_with_test_data
from bobweb.bob.tests_mocks_v2 import init_chat_user
from bobweb.bob.tests_msg_btn_utils import buttons_from_reply_markup, assert_buttons_equal_to_reply_markup
from bobweb.bob.tests_utils import MockResponse, assert_command_triggers, mock_response_with_code


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


# Define frozen time that is included in the mock data set
@freeze_time(datetime.datetime(2023, 2, 17))
# By default, if nothing else is defined, all request.get requests are returned with this mock
@mock.patch('requests.get', mock_response_200_with_test_data)
class SahkoCommandTestsWithTodayInCacheTests(TestCase):
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


# By default, if nothing else is defined, all request.get requests are returned with this mock
@mock.patch('requests.get', mock_response_200_with_test_data)
class SahkoCommandTestsWithoutGlobalFreezeTime(TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super(SahkoCommandTestsWithoutGlobalFreezeTime, cls).setUpClass()
        SahkoCommand.run_async = False

    # Set datetime to 16.2.2023 on which test data contains that and the next date
    @freeze_time(datetime.datetime(2023, 2, 16), as_kwarg='clock')
    def test_tomorrow_button_is_shown_in_correct_moments(self, clock: FrozenDateTimeFactory):
        # First situation where there is cached data for current date and the next date
        chat, user = init_chat_user()
        user.send_message('/sahko')
        self.assertEqual(2, len(NordpoolCache.cache))

        expected_buttons = [show_graph_btn, info_btn, show_tomorrow_btn]
        assert_buttons_equal_to_reply_markup(self, expected_buttons, chat.last_bot_msg().reply_markup)

        # Now tick time ahead to next day. Now 'Tomorrow' should not be in the buttons
        clock.tick(datetime.timedelta(days=1))
        user.send_message('/sahko')
        expected_buttons = [show_graph_btn, info_btn]
        assert_buttons_equal_to_reply_markup(self, expected_buttons, chat.last_bot_msg().reply_markup)

    # Set datetime to 16.2.2023 on which test data contains that and the next date
    @freeze_time(datetime.datetime(2023, 2, 16), as_kwarg='clock')
    def test_sahko_message_should_always_have_latest_data_after_update(self, clock: FrozenDateTimeFactory):
        # First check that message contains data for current date
        chat, user = init_chat_user()
        user.send_message('/sahko')
        self.assertIn('16.02.2023', chat.last_bot_txt())

        clock.tick(datetime.timedelta(days=1))
        # Now that the day have changed, when user switches to the info page and back
        # the message should display data for current date
        user.press_button(info_btn.text)
        user.press_button(back_button.text)
        self.assertIn('17.02.2023', chat.last_bot_txt())

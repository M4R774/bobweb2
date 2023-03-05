import datetime

from unittest import mock
from django.test import TestCase

from freezegun import freeze_time
from freezegun.api import FrozenDateTimeFactory

from bobweb.bob import main, command_sahko, database
from bobweb.bob.activities.activity_state import back_button
from bobweb.bob.command_sahko import SahkoCommand, show_graph_btn, hide_graph_btn, show_tomorrow_btn, info_btn, \
    graph_width_sub_btn, graph_width_add_btn

from bobweb.bob.nordpool_service import NordpoolCache
from bobweb.bob.test_nordpool_service import mock_response_200_with_test_data, expected_data_point_count
from bobweb.bob.tests_mocks_v2 import init_chat_user, MockUser, MockChat
from bobweb.bob.tests_msg_btn_utils import assert_buttons_equal_to_reply_markup
from bobweb.bob.tests_utils import assert_command_triggers, mock_response_with_code


sahko_command = '/sahko'


@mock.patch('requests.get', mock_response_with_code(status_code=400, content={}))
class SahkoCommandFetchOrProcessError(TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super(SahkoCommandFetchOrProcessError, cls).setUpClass()
        SahkoCommand.run_async = False

    def test_should_inform_if_fetch_failed(self):
        SahkoCommand.run_async = False
        chat, user = init_chat_user()
        user.send_message(sahko_command)
        self.assertIn(command_sahko.fetch_failed_msg, chat.last_bot_txt())


# Define frozen time that is included in the mock data set. Mock data contains data for 10.-17.2.2023
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
        should_trigger = [sahko_command, '!sahko', '.sahko', '/SAHKO', '/sähkö', '/sahkö', '/sähko']
        should_not_trigger = ['sahko', 'test /sahko', '/sahko test']
        assert_command_triggers(self, SahkoCommand, should_trigger, should_not_trigger)

    def test_should_contain_price_now(self):
        chat, user = init_chat_user()
        user.send_message(sahko_command)
        self.assertIn('hinta nyt    3.47', chat.last_bot_txt())

    def test_graph_can_be_toggled_on_and_off(self):
        chat, user = init_chat_user()
        user.send_message(sahko_command)
        # First should have no grap, then after first button press graph should appear and after second disappear again
        expected_graph_slice = '9░░░░░░░▆███████▁░░░░░░░░'
        self.assertNotIn(expected_graph_slice, chat.last_bot_txt())
        user.press_button(show_graph_btn)
        self.assertIn(expected_graph_slice, chat.last_bot_txt())
        user.press_button(hide_graph_btn)
        self.assertNotIn(expected_graph_slice, chat.last_bot_txt())

    # Set datetime to 16.2.2023 on which test data contains that and the next date
    @freeze_time(datetime.datetime(2023, 2, 16), as_kwarg='clock')
    def test_tomorrow_button_is_shown_in_correct_moments(self, clock: FrozenDateTimeFactory):
        # First situation where there is cached data for current date and the next date
        chat, user = init_chat_user()
        user.send_message(sahko_command)
        self.assertEqual(expected_data_point_count, len(NordpoolCache.cache))

        expected_buttons = [show_graph_btn, info_btn, show_tomorrow_btn]
        assert_buttons_equal_to_reply_markup(self, expected_buttons, chat.last_bot_msg().reply_markup)

        # Now tick time ahead to next day. Now 'Tomorrow' should not be in the buttons
        clock.tick(datetime.timedelta(days=1))
        user.send_message(sahko_command)
        expected_buttons = [show_graph_btn, info_btn]
        assert_buttons_equal_to_reply_markup(self, expected_buttons, chat.last_bot_msg().reply_markup)

    # Set datetime to 16.2.2023 on which test data contains that and the next date
    @freeze_time(datetime.datetime(2023, 2, 16), as_kwarg='clock')
    def test_sahko_message_should_always_have_latest_data_after_update(self, clock: FrozenDateTimeFactory):
        # First check that message contains data for current date
        chat, user = init_chat_user()
        user.send_message(sahko_command)
        self.assertIn('16.02.2023', chat.last_bot_txt())

        clock.tick(datetime.timedelta(days=1))
        # Now that the day have changed, when user switches to the info page and back
        # the message should display data for current date
        user.press_button(info_btn)
        user.press_button(back_button)
        self.assertIn('17.02.2023', chat.last_bot_txt())

    def test_when_no_graph_width_saved_for_chat(self, chat: MockChat = None, user: MockUser = None):
        if chat is None and user is None:
            chat, user = init_chat_user()

        # 1. Check that graph is returned with width of 24 chars
        user.send_message(sahko_command)
        user.press_button(show_graph_btn)
        expected_graph_slice = '░░░░░░░▆███████▁░░░░░░░░'
        self.assertEqual(24, len(expected_graph_slice))
        self.assertIn(f'9{expected_graph_slice}\n', chat.last_bot_txt())

        # 2. Check that buttons only contain buttons for subtracting from the width
        expected_buttons = [hide_graph_btn, graph_width_sub_btn, info_btn]
        assert_buttons_equal_to_reply_markup(self, expected_buttons, chat.last_bot_msg().reply_markup)

    def test_when_subtract_width_is_pressed_width_is_subtracted(self):
        chat, user = init_chat_user()
        self.test_when_no_graph_width_saved_for_chat(chat, user)

        # 1. Subtract width by one character. Now subtract message should have a subtract button
        user.press_button(graph_width_sub_btn)
        expected_graph_slice = '░░░░░░░███████▅░░░░░░░░'
        self.assertEqual(23, len(expected_graph_slice))
        self.assertIn(f'9{expected_graph_slice}\n', chat.last_bot_txt())

        # 2. Now buttons contain buttons for subtracting and adding width to the graph
        expected_buttons = [hide_graph_btn, graph_width_sub_btn, graph_width_add_btn, info_btn]
        assert_buttons_equal_to_reply_markup(self, expected_buttons, chat.last_bot_msg().reply_markup)

    def test_when_graph_width_is_1_no_subtract_button_is_shown(self):
        chat, user = init_chat_user()
        chat_entity = database.get_chat(chat.id)
        chat_entity.nordpool_graph_width = 1
        chat_entity.save()

        user.send_message(sahko_command)
        user.press_button(show_graph_btn)

        expected_graph_slice = '░'
        self.assertEqual(1, len(expected_graph_slice))
        self.assertIn(f'9{expected_graph_slice}\n', chat.last_bot_txt())

        expected_buttons = [hide_graph_btn, graph_width_add_btn, info_btn]
        assert_buttons_equal_to_reply_markup(self, expected_buttons, chat.last_bot_msg().reply_markup)


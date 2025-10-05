import asyncio
import datetime
import json
from unittest import mock

import django
import pytest
from django.core import management
from django.test import TestCase
from freezegun import freeze_time
from telegram.constants import ParseMode

from bot import main, twitch_service, command_service, message_board_service
from bot.commands.twitch import TwitchCommand, TwitchStreamUpdatedSteamStatusState
from bot.message_board import MessageBoard
from bot.test_message_board_command_and_service import setup_service_and_create_board, \
    mock_schedules_by_week_day, FULL_TICK, end_all_message_board_background_task
from bot.test_twitch_service import twitch_stream_mock_response, twitch_stream_is_live_expected_message, \
    twitch_stream_has_ended_expected_message
from bot.tests_mocks_v2 import init_chat_user, mock_async_get_bytes
from bot.tests_utils import assert_command_triggers, mock_async_get_json, \
    async_raise_client_response_error
from bot.twitch_service import TwitchService

GET_JSON_PATH = 'bot.async_http.get_json'
TWITCH_COMMAND = '/twitch'
TWITCH_COMMAND_TWITCHDEV_CHANNEL = '/twitch twitchdev'
TWITCHDEV_STREAM_IS_LIVE = '<b>🔴 TwitchDev on LIVE! 🔴</b>'


@pytest.mark.asyncio
class TwitchCommandTests(django.test.TransactionTestCase):
    # test_epic_games käytetty esimerkkinä

    @classmethod
    def setUpClass(cls) -> None:
        super(TwitchCommandTests, cls).setUpClass()
        management.call_command('migrate')
        # For tests, set update interval to 0 seconds
        TwitchStreamUpdatedSteamStatusState.update_interval_in_seconds = 0

    async def test_command_triggers(self):
        # Should trigger on standard command as well when twitch channel link is sent to chat
        should_trigger = [
            TWITCH_COMMAND,
            '!twitch',
            '.twitch',
            TWITCH_COMMAND.upper(),
            '/twitch test',
            '/twitch https://www.twitch.tv/twitchdev',
            # https and www are optional
            '/twitch https://twitch.tv/twitchdev',
            '/twitch www.twitch.tv/twitchdev',
            '/twitch twitch.tv/twitchdev',
            # Link can be anywhere in the message
            '/twitch test twitch.tv/twitchdev test',
        ]
        should_not_trigger = [
            'twitch',
            'test twitch',
            # link without the command does not trigger the command
            'https://www.twitch.tv/twitchdev',
            'www.twitch.tv/twitchdev',
            'twitch.tv/twitchdev'
        ]
        await assert_command_triggers(self, TwitchCommand, should_trigger, should_not_trigger)

    async def test_no_command_parameter_gives_help_text(self):
        chat, user = init_chat_user()
        await user.send_message(TWITCH_COMMAND)
        self.assertEqual('Anna komennon parametrina kanavan nimi tai linkki kanavalle', chat.last_bot_txt())
        self.assertEqual(1, len(chat.bot.messages))

    async def test_request_error_gives_error_text_response(self):
        # Gives error, as no twitch service with real access token initiated while testing
        chat, user = init_chat_user()
        with (
            mock.patch(GET_JSON_PATH, async_raise_client_response_error(status=999)),
            self.assertLogs(level='ERROR') as log
        ):
            await user.send_message(TWITCH_COMMAND_TWITCHDEV_CHANNEL)
        self.assertEqual('Yhteyden muodostaminen Twitchin palvelimiin epäonnistui 🔌✂️', chat.last_bot_txt())
        self.assertIn('Failed to get stream status for twitchdev. Request returned with response code 999',
                      log.output[0])
        self.assertEqual(1, len(chat.bot.messages))

    @mock.patch(GET_JSON_PATH, async_raise_client_response_error(status=400))
    async def test_bad_request_400_no_channel_found_with_given_name(self):
        """ Tests that if channel-request to twitch returns with response 400 Bad Request, that means that no channel
            exists with given name. """
        twitch_service.instance = TwitchService('123')  # Mock service

        chat, user = init_chat_user()
        await user.send_message('/twitch _NOT_EXISTING_NAME_')
        self.assertEqual('Annetun nimistä Twitch kanavaa ei ole olemassa', chat.last_bot_txt())
        self.assertEqual(1, len(chat.bot.messages))

    @mock.patch(GET_JSON_PATH, mock_async_get_json({'data': []}))
    async def test_request_ok_no_stream_found(self):
        """ Tests that if channel-request to twitch returns with response 200 ok that has data attribute with an empty
            list it means that the channel is not live. """
        twitch_service.instance = TwitchService('123')  # Mock service

        chat, user = init_chat_user()
        await user.send_message(TWITCH_COMMAND_TWITCHDEV_CHANNEL)
        self.assertEqual('Kanava ei striimaa nyt mitään', chat.last_bot_txt())
        self.assertEqual(1, len(chat.bot.messages))

    # Mock actual twitch api call with predefined response
    @mock.patch(GET_JSON_PATH, mock_async_get_json(json.loads(twitch_stream_mock_response)))
    # Overrides actual network call with mock that returns predefined image
    @mock.patch('bot.async_http.get_content_bytes', mock_async_get_bytes(bytes(1)))
    @freeze_time(datetime.datetime(2024, 1, 1, 0, 0, 0))
    async def test_request_ok_stream_response_found(self):
        """ Tests that if response is returned stream status is sent by the bot.
            All GET-requests are mocked with mock-data. Bot responses with 2 messages. The first containing a stream
            thumbnail and the second containing the status message """
        twitch_service.instance = TwitchService('123')  # Mock service
        chat, user = init_chat_user()
        await user.send_message(TWITCH_COMMAND_TWITCHDEV_CHANNEL)

        self.assertEqual(1, len(chat.bot.messages))
        # Should have expected image with the message
        # The first message from bot should have expected image
        self.assertEqual(bytes(1), chat.last_bot_msg().photo)

        # The second should have the status message
        # Note! The api gives UTC +/- 0 times. Bot localizes the time to Finnish local time
        # Note! For image messages, text is in 'caption'-attribute
        self.assertEqual(twitch_stream_is_live_expected_message, chat.last_bot_txt())
        self.assertEqual(chat.last_bot_msg().parse_mode, ParseMode.HTML)
        await command_service.instance.current_activities[0].done()  # Remove from activities

    # Mock actual twitch api call with predefined response
    # Overrides actual network call with mock that returns predefined image
    @mock.patch('bot.async_http.get_content_bytes', mock_async_get_bytes(b'\0'))
    @mock.patch('bot.async_http.get_content_bytes', mock_async_get_bytes(b'\0'))
    @freeze_time(datetime.datetime(2024, 1, 1, 0, 0, 0))
    async def test_stream_end_procedure(self):
        """ Test that the stream end procedure is done as expected. """
        command_service.instance.current_activities = []
        twitch_service.instance = TwitchService('123')  # Mock service
        chat, user = init_chat_user()

        with mock.patch(GET_JSON_PATH, mock_async_get_json(json.loads(twitch_stream_mock_response))):
            await user.send_message(TWITCH_COMMAND_TWITCHDEV_CHANNEL)

        self.assertIn(TWITCHDEV_STREAM_IS_LIVE, chat.last_bot_txt())

        # Now that the stream is active, test how the stream end procedure works. First find and check the activity.
        current_activities = command_service.instance.current_activities
        self.assertEqual(1, len(current_activities))
        twitch_activity_state: TwitchStreamUpdatedSteamStatusState = current_activities[0].state

        # Manually activate stream status update with empty response
        with mock.patch(GET_JSON_PATH, mock_async_get_json({'data': []})):
            await twitch_activity_state.wait_and_update_task()

        self.assertEqual(twitch_stream_has_ended_expected_message, chat.last_bot_txt())
        # Check that the activity has been removed from current activities
        await asyncio.sleep(0)  # Wait for the activity to be removed
        self.assertEqual(0, len(current_activities))


@pytest.mark.asyncio
class TwitchMessageBoardEventTests(django.test.TransactionTestCase):
    """ Tests to make sure that when the chat has active message board and twitch command is sent, the stream status
        is tracked in the event message as well. """
    @classmethod
    def setUpClass(cls) -> None:
        super(TwitchMessageBoardEventTests, cls).setUpClass()
        management.call_command('migrate')
        # For tests, set update interval to 0 seconds
        MessageBoard._board_event_update_interval_in_seconds = FULL_TICK
        # For tests, set update interval to 0 seconds
        TwitchStreamUpdatedSteamStatusState.update_interval_in_seconds = 0
        message_board_service.schedules_by_week_day = mock_schedules_by_week_day

    def tearDown(self):
        super().tearDown()
        end_all_message_board_background_task()

    @mock.patch('bot.async_http.get_content_bytes', mock_async_get_bytes(b'\0'))
    @mock.patch('bot.commands.twitch.fetch_stream_frame', mock_async_get_bytes(b'\0'))
    async def test_twitch_stream_status_is_added_as_event_message_if_chat_is_using_message_board(self):
        """ When twitch command is given, active stream is found and the chat is using message board,
            then the stream status is added as an event to the board and its content is updated as the
            stream status is updated. """

        command_service.instance.current_activities = []
        twitch_service.instance = TwitchService('123')  # Mock service
        chat, user, board = await setup_service_and_create_board()
        board_message = chat.bot.messages[0]

        with mock.patch(GET_JSON_PATH, mock_async_get_json(json.loads(twitch_stream_mock_response))):
            await user.send_message(TWITCH_COMMAND_TWITCHDEV_CHANNEL)

        await asyncio.sleep(FULL_TICK)  # Wait for the activity to be removed

        # Now there should be an event message on the board and latest bots message should bot contain stream status
        self.assertIn(TWITCHDEV_STREAM_IS_LIVE, board_message.text)
        self.assertIn(TWITCHDEV_STREAM_IS_LIVE, chat.last_bot_txt())

        # Manually activate stream status update with empty response
        current_activities = command_service.instance.current_activities
        self.assertEqual(1, len(current_activities))
        twitch_activity_state: TwitchStreamUpdatedSteamStatusState = current_activities[0].state
        with mock.patch(GET_JSON_PATH, mock_async_get_json({'data': []})):
            await twitch_activity_state.wait_and_update_task()

        await asyncio.sleep(FULL_TICK)  # Wait for the activity to be removed

        # Now both the latest message and the message board have been updated.
        # Message board event has been removed and the board now only contains scheduled message
        self.assertEqual(0, len(board._event_messages))
        self.assertEqual(board._scheduled_message.body, board_message.text)
        self.assertEqual(None, board._current_event_id)
        self.assertIn('<b>Kanavan TwitchDev striimi on päättynyt 🏁</b>', chat.last_bot_txt())

import datetime
import json
from unittest import mock

import django
import pytest
from django.core import management
from django.test import TestCase
from freezegun import freeze_time
from telegram.constants import ParseMode

from bobweb.bob import main, twitch_service, command_twitch, command_service
from bobweb.bob.command import ChatCommand
from bobweb.bob.command_twitch import TwitchCommand, TwitchStreamUpdatedSteamStatusState
from bobweb.bob.test_twitch_service import twitch_stream_mock_response
from bobweb.bob.tests_mocks_v2 import init_chat_user, mock_async_get_image
from bobweb.bob.tests_utils import assert_command_triggers, mock_async_get_json, AsyncMock
from bobweb.bob.twitch_service import TwitchService, StreamStatus


@pytest.mark.asyncio
# test_epic_games käytetty esimerkkinä
class TwitchCommandTests(django.test.TransactionTestCase):
    command_class: ChatCommand.__class__ = TwitchCommand
    command_str: str = 'twitch'

    @classmethod
    def setUpClass(cls) -> None:
        super(TwitchCommandTests, cls).setUpClass()
        management.call_command('migrate')

    async def test_command_triggers(self):
        # Should trigger on standard command as well when twitch channel link is sent to chat
        should_trigger = [
            f'/{self.command_str}',
            f'!{self.command_str}',
            f'.{self.command_str}',
            f'/{self.command_str.upper()}',
            f'/{self.command_str} test',
            f'/{self.command_str} https://www.twitch.tv/twitchdev',
            # https and www are optional
            'https://www.twitch.tv/twitchdev',
            'https://twitch.tv/twitchdev',
            'www.twitch.tv/twitchdev',
            'twitch.tv/twitchdev',
            # Link can be anywhere in the message
            'test twitch.tv/twitchdev test',
        ]
        should_not_trigger = [f'{self.command_str}', f'test /{self.command_str}']
        await assert_command_triggers(self, self.command_class, should_trigger, should_not_trigger)

    async def test_no_command_parameter_gives_help_text(self):
        chat, user = init_chat_user()
        await user.send_message('/twitch')
        self.assertEqual('Anna komennon parametrina kanavan nimi tai linkki kanavalle', chat.last_bot_txt())
        self.assertEqual(1, len(chat.bot.messages))

    async def test_request_error_gives_error_text_response(self):
        # Gives error, as no twitch service with real access token initiated while testing
        chat, user = init_chat_user()
        await user.send_message('/twitch twitchdev')
        self.assertEqual('Yhteyden muodostaminen Twitchin palvelimiin epäonnistui 🔌✂️', chat.last_bot_txt())
        self.assertEqual(1, len(chat.bot.messages))

    @mock.patch('bobweb.bob.async_http.get_json', mock_async_get_json({'data': []}))
    async def test_request_ok_no_stream_found(self):
        """ Tests that if channel-request to twitch returns with response 200 ok that has data attribute with an empty
            list it means that the channel is not live. """
        twitch_service.instance = TwitchService('123')  # Mock service

        chat, user = init_chat_user()
        await user.send_message('/twitch twitchdev')
        self.assertEqual('Annettua kanavaa ei löytynyt tai sillä ei ole striimi live', chat.last_bot_txt())
        self.assertEqual(1, len(chat.bot.messages))

    # Mock actual twitch api call with predefined response
    @mock.patch('bobweb.bob.async_http.get_json', mock_async_get_json(json.loads(twitch_stream_mock_response)))
    # Overrides actual network call with mock that returns predefined image
    @mock.patch('bobweb.bob.async_http.get_content_bytes', mock_async_get_image)
    # Overrides actual wait_and_update_task() so that the test is not left waiting for next stream update
    @mock.patch.object(command_twitch.TwitchStreamUpdatedSteamStatusState, 'wait_and_update_task', AsyncMock())
    @freeze_time(datetime.datetime(2024, 1, 1, 0, 0, 0))
    async def test_request_ok_stream_response_found(self):
        """ Tests that if response is returned stream status is sent by the bot.
            All GET-requests are mocked with mock-data. Bot responses with 2 messages. The first containing a stream
            thumbnail and the second containing the status message """
        twitch_service.instance = TwitchService('123')  # Mock service
        chat, user = init_chat_user()
        await user.send_message('/twitch twitchdev')

        self.assertEqual(1, len(chat.bot.messages))
        # Should have expected image with the message
        with open('bobweb/bob/resources/test/red_1x1_pixel.jpg', "rb") as file:
            # The first message from bot should have expected image
            self.assertEqual(file.read(), chat.last_bot_msg().photo.read())

        # The second should have the status message
        # Note! The api gives UTC +/- 0 times. Bot localizes the time to Finnish local time
        # Note! For image messages, text is in 'caption'-attribute
        self.assertEqual('<b>🔴 TwitchDev on LIVE! 🔴</b>\n'
                         '<i>stream title</i>\n\n'
                         '🎮 Peli: python\n'
                         '👀 Katsojia: 999\n'
                         '🕒 Striimi alkanut: klo 14:00\n\n'
                         'Katso livenä! www.twitch.tv/twitchdev\n'
                         '(Viimeisin päivitys klo 02:00:00)',
                         chat.last_bot_txt())
        self.assertEqual(chat.last_bot_msg().parse_mode, ParseMode.HTML)
        await command_service.instance.current_activities[0].done()  # Remove from activities

    # Mock actual twitch api call with predefined response
    # Overrides actual network call with mock that returns predefined image
    @mock.patch('bobweb.bob.async_http.get_content_bytes', mock_async_get_image)
    # Overrides actual wait_and_update_task() so that the test is not left waiting for next stream update
    @mock.patch.object(command_twitch.TwitchStreamUpdatedSteamStatusState, 'wait_and_update_task', AsyncMock())
    @freeze_time(datetime.datetime(2024, 1, 1, 0, 0, 0))
    async def test_stream_end_procedure(self):
        """ Test that the stream end procedure is done as expected. """
        command_service.instance.current_activities = []
        twitch_service.instance = TwitchService('123')  # Mock service
        chat, user = init_chat_user()

        with mock.patch('bobweb.bob.async_http.get_json', mock_async_get_json(json.loads(twitch_stream_mock_response))):
            await user.send_message('/twitch twitchdev')

        self.assertIn('<b>🔴 TwitchDev on LIVE! 🔴</b>', chat.last_bot_txt())

        # Now that the stream is active, test how the stream end procedure works. First find and check the activity.
        current_activities = command_service.instance.current_activities
        self.assertEqual(1, len(current_activities))
        twitch_activity_state: TwitchStreamUpdatedSteamStatusState = current_activities[0].state

        # Manually activate stream status update with empty response
        with mock.patch('bobweb.bob.async_http.get_json', mock_async_get_json({'data': []})):
            await twitch_activity_state.update_stream_status_message()

        self.assertEqual('<b>Kanavan TwitchDev striimi on päättynyt 🏁</b>\n'
                         '<i>stream title</i>\n\n'
                         '🎮 Peli: python\n'
                         '🕒 Striimattu: klo 14:00 - 02:00\n\n'  # API uses UTC, times localized to Finnish time zone
                         'Kanava: www.twitch.tv/twitchdev',
                         chat.last_bot_txt())
        # Check that the activity has been removed from current activities
        self.assertEqual(0, len(current_activities))

    # To assure that the stream status is formatted to message as expected
    @freeze_time(datetime.datetime(2024, 1, 1, 12, 30, 0))
    def test_StreamStatus_to_message_with_html_parse_mode(self):
        # Create stream status object with only values that affect the time output
        status = StreamStatus(user_login='twitchtv',
                              user_name='TwitchTv',
                              stream_is_live=True)

        # When stream is live, should have only the time when the stream has started
        status.started_at_utc = datetime.datetime(2024, 1, 1, 12, 30, 0)
        self.assertIn('🕒 Striimi alkanut: klo 14:30', status.to_message_with_html_parse_mode())

        # If stream has started on a different day other than today, should have time when the stream started
        status.started_at_utc = datetime.datetime(2024, 1, 2, 12, 30, 0)
        self.assertIn('🕒 Striimi alkanut: 2.1.2024 klo 14:30', status.to_message_with_html_parse_mode())

        # Now if the stream has ended
        status.stream_is_live = False

        # Stream has ended on the same day
        status.started_at_utc = datetime.datetime(2024, 1, 1, 12, 30, 0)
        status.ended_at_utc = datetime.datetime(2024, 1, 1, 14, 0, 0)
        self.assertIn('🕒 Striimattu: klo 14:30 - 16:00', status.to_message_with_html_parse_mode())

        # And if the stream has ended and the stream started and ended on a different date, should have time with dates
        status.started_at_utc = datetime.datetime(2024, 1, 1, 12, 30, 0)
        status.ended_at_utc = datetime.datetime(2024, 1, 2, 14, 0, 0)
        self.assertIn('🕒 Striimattu: 1.1.2024 klo 14:30 - 2.1.2024 klo 16:00', status.to_message_with_html_parse_mode())

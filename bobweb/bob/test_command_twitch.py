import json
from unittest import mock

import django
import freezegun
import pytest
from django.core import management
from django.test import TestCase
from telegram.constants import ParseMode

from bobweb.bob import main, twitch_service
from bobweb.bob.command import ChatCommand
from bobweb.bob.command_twitch import TwitchCommand
from bobweb.bob.test_twitch_service import twitch_stream_mock_response
from bobweb.bob.tests_mocks_v2 import init_chat_user, mock_async_get_image
from bobweb.bob.tests_utils import assert_command_triggers, mock_async_get_json
from bobweb.bob.twitch_service import TwitchService


# test_epic_games käytetty esimerkkinä

# By default, if nothing else is defined, all request.get requests are returned with this mock
@pytest.mark.asyncio
# @mock.patch('bobweb.bob.async_http.get_json', mock_fetch_json)
# @mock.patch('bobweb.bob.async_http.get_all_content_bytes_concurrently', mock_fetch_all_content_bytes)
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

    @mock.patch('bobweb.bob.async_http.get_json', mock_async_get_json(json.loads(twitch_stream_mock_response)))
    @mock.patch('bobweb.bob.async_http.get_content_bytes', mock_async_get_image)
    async def test_request_ok_stream_response_found(self):
        """ Tests that if response is returned stream status is sent by the bot.
            All GET-requests are mocked with mock-data. """
        twitch_service.instance = TwitchService('123')  # Mock service

        chat, user = init_chat_user()
        await user.send_message('/twitch twitchdev')
        # Note! The api gives UTC +/- 0 times. Bot localizes the time to Finnish local time
        self.assertEqual('<b>🔴 TwitchDev on LIVE! 🔴</b>\n'
                         '<i>stream title</i>\n\n'
                         '🎮 Peli: python\n'
                         '👀 Katsojia: 999\n'
                         '🕒 Striimi alkanut: 01.01.2024 14:00\n\n'
                         'Katso livenä! <a href="www.twitch.tv/twitchdev">twitch.tv/twitchdev</a>',
                         chat.last_bot_txt())
        self.assertEqual(chat.last_bot_msg().parse_mode, ParseMode.HTML)
        self.assertEqual(1, len(chat.bot.messages))

        # Should have expected image with the message
        with open('bobweb/bob/resources/test/red_1x1_pixel.jpg', "rb") as file:
            self.assertEqual(file.read(), chat.last_bot_msg().photo.read())

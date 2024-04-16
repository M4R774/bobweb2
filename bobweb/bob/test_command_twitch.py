from unittest import mock

import django
import pytest
from django.core import management
from django.test import TestCase

from bobweb.bob import twitch_service
from bobweb.bob.command import ChatCommand
from bobweb.bob.command_twitch import TwitchCommand
from bobweb.bob.tests_mocks_v2 import init_chat_user
from bobweb.bob.tests_utils import assert_command_triggers, mock_fetch_json_with_content
from bobweb.bob.twitch_service import TwitchService


# test_epic_games käytetty esimerkkinä

# By default, if nothing else is defined, all request.get requests are returned with this mock
@pytest.mark.asyncio
# @mock.patch('bobweb.bob.async_http.get_json', mock_fetch_json)
# @mock.patch('bobweb.bob.async_http.fetch_all_content_bytes', mock_fetch_all_content_bytes)
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
        self.assertIn('Anna komennon parametrina kanavan nimi tai linkki kanavalle', chat.last_bot_txt())

    async def test_request_error_gives_error_text_response(self):
        # Gives error, as no twitch service with real access token initiated while testing
        chat, user = init_chat_user()
        await user.send_message('/twitch twitchdev')
        self.assertIn('Yhteyden muodostaminen Twitchin palvelimiin epäonnistui 🔌✂️', chat.last_bot_txt())


    @mock.patch('bobweb.bob.async_http.get_json', mock_fetch_json_with_content({'data': []}))
    async def test_request_ok_no_stream_found(self):
        twitch_service.instance = TwitchService('123')  # Mock service

        chat, user = init_chat_user()
        await user.send_message('/twitch twitchdev')
        self.assertIn('Annettua kanavaa ei löytynyt tai sillä ei ole striimi live', chat.last_bot_txt())



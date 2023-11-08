from unittest import mock

import django
import pytest
from django.test import TestCase

import bobweb.bob.config
from bobweb.bob.command import ChatCommand
from bobweb.bob.command_speech import SpeechCommand
from bobweb.bob.tests_mocks_v2 import init_chat_user
from bobweb.bob.tests_utils import assert_command_triggers


async def speech_api_mock_response_200(*args, **kwargs):
    return str.encode('this is hello.mp3 in bytes')


@pytest.mark.asyncio
@mock.patch('bobweb.bob.openai_api_utils.user_has_permission_to_use_openai_api', lambda *args: True)
@mock.patch('bobweb.bob.async_http.post_expect_bytes', speech_api_mock_response_200)
class SpeechCommandTest(django.test.TransactionTestCase):
    bobweb.bob.config.openai_api_key = 'DUMMY_VALUE_FOR_ENVIRONMENT_VARIABLE'
    command_class: ChatCommand.__class__ = SpeechCommand
    command_str: str = 'lausu'

    @classmethod
    def setUpClass(cls) -> None:
        super(SpeechCommandTest, cls).setUpClass()
        cls.maxDiff = None

    async def test_command_triggers(self):
        should_trigger = [f'/{self.command_str}', f'!{self.command_str}', f'.{self.command_str}',
                          f'/{self.command_str.upper()}']
        should_not_trigger = [f'{self.command_str}', f'test /{self.command_str}', f'/{self.command_str} test']
        await assert_command_triggers(self, self.command_class, should_trigger, should_not_trigger)

    async def test_when_not_reply_gives_help_text(self):
        chat, user = init_chat_user()
        await user.send_message('/lausu')
        self.assertEqual('Lausu viesti ääneen vastaamalla siihen komennolla \'\\lausu\'',
                         chat.last_bot_txt())

    async def test_too_long_title_gets_cut(self):
        chat, user = init_chat_user()
        message = await user.send_message('this is a too long prompt to be in title fully')
        await user.send_message('/lausu', reply_to_message=message)
        self.assertEqual('this is a ',
                         chat.last_bot_txt())

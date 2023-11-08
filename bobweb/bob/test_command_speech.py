from unittest import mock

import django
import pytest
from django.test import TestCase

from bobweb.bob.command import ChatCommand
from bobweb.bob.command_speech import SpeechCommand
from bobweb.bob.tests_mocks_v2 import init_chat_user
from bobweb.bob.tests_utils import assert_command_triggers


@pytest.mark.asyncio
@mock.patch('bobweb.bob.openai_api_utils.user_has_permission_to_use_openai_api', lambda *args: True)
class SpeechCommandTest(django.test.TransactionTestCase):
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

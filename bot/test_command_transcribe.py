from unittest import mock

import django
import pytest
from django.test import TestCase

from bot.command import ChatCommand
from bot.command_transcribe import TranscribeCommand
from bot.tests_mocks_v2 import init_chat_user
from bot.tests_utils import assert_command_triggers


@pytest.mark.asyncio
@mock.patch('bot.openai_api_utils.user_has_permission_to_use_openai_api', lambda *args: True)
class TranscribeCommandTest(django.test.TransactionTestCase):
    command_class: ChatCommand.__class__ = TranscribeCommand
    command_str: str = 'tekstitä'

    @classmethod
    def setUpClass(cls) -> None:
        super(TranscribeCommandTest, cls).setUpClass()
        cls.maxDiff = None

    async def test_command_triggers(self):
        should_trigger = [f'/{self.command_str}', f'!{self.command_str}', f'.{self.command_str}',
                          f'/{self.command_str.upper()}']
        should_not_trigger = [f'{self.command_str}', f'test /{self.command_str}', f'/{self.command_str} test']
        await assert_command_triggers(self, self.command_class, should_trigger, should_not_trigger)

    async def test_when_not_reply_gives_help_text(self):
        chat, user = init_chat_user()
        await user.send_message('/tekstitä')
        self.assertEqual('Tekstitä mediaa sisältävä viesti vastaamalla siihen komennolla \'\\tekstitä\'',
                         chat.last_bot_txt())

    async def test_when_reply_but_target_message_has_no_media_gives_help_text(self):
        chat, user = init_chat_user()
        msg_without_media = await user.send_message('hi')
        await user.send_message('/tekstitä', reply_to_message=msg_without_media)
        self.assertEqual('Kohteena oleva viesti ei ole ääniviesti, äänitiedosto tai videotiedosto jota '
                         'voisi tekstittää', chat.last_bot_txt())

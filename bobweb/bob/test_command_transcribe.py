import io
from unittest import mock, skip

import openai
from django.test import TestCase

from telegram import Voice, File

from bobweb.bob import main, database
from bobweb.bob.command import ChatCommand
from bobweb.bob.command_transcribe import TranscribeCommand
from bobweb.bob.tests_mocks_v2 import init_chat_user
from bobweb.bob.tests_utils import assert_command_triggers, MockResponse


@mock.patch('bobweb.bob.openai_api_utils.user_has_permission_to_use_openai_api', lambda *args: True)
class TranscribeCommandTest(TestCase):
    command_class: ChatCommand.__class__ = TranscribeCommand
    command_str: str = 'tekstitä'

    @classmethod
    def setUpClass(cls) -> None:
        super(TranscribeCommandTest, cls).setUpClass()
        cls.maxDiff = None

    def test_command_triggers(self):
        should_trigger = [f'/{self.command_str}', f'!{self.command_str}', f'.{self.command_str}',
                          f'/{self.command_str.upper()}']
        should_not_trigger = [f'{self.command_str}', f'test /{self.command_str}', f'/{self.command_str} test']
        assert_command_triggers(self, self.command_class, should_trigger, should_not_trigger)

    def test_when_not_reply_gives_help_text(self):
        chat, user = init_chat_user()
        user.send_message('/tekstitä')
        self.assertEqual('Tekstitä mediaa sisältävä viesti vastaamalla siihen komennolla \'\\tekstitä\'',
                         chat.last_bot_txt())

    def test_when_reply_but_target_message_has_no_media_gives_help_text(self):
        chat, user = init_chat_user()
        msg_without_media = user.send_message('hi')
        user.send_message('/tekstitä', reply_to_message=msg_without_media)
        self.assertEqual('Kohteena oleva viesti ei ole ääniviesti, äänitiedosto tai videotiedosto jota '
                         'voisi tekstittää', chat.last_bot_txt())

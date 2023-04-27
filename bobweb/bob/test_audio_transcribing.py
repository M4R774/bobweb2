from unittest import mock, skip
from django.test import TestCase
from openai.openai_response import OpenAIResponse

from telegram import Voice, File

from bobweb.bob import main, database
from bobweb.bob.command import ChatCommand
from bobweb.bob.command_transcribe import TranscribeCommand
from bobweb.bob.tests_mocks_v2 import init_chat_user
from bobweb.bob.tests_utils import assert_command_triggers, assert_reply_equal, assert_reply_to_contain


class VoiceMessageHandlerTest(TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super(VoiceMessageHandlerTest, cls).setUpClass()
        cls.maxDiff = None

    @skip  # Should not be run with other tests as this is only created to helpo development and possible debugging
    @mock.patch('bobweb.bob.openai_api_utils.user_has_permission_to_use_openai_api', lambda *args: True)
    @mock.patch('os.getenv', lambda key: 'DUMMY_VALUE_FOR_ENVIRONMENT_VARIABLE')
    def test_transcribe_audio_file(self):
        """ Development time test that calls real API. Created for faster debugging and testing """
        with open('bobweb/bob/resources/test/file_0.oga', "rb") as test_sound_file:
            chat, user = init_chat_user()
            chat_entity = database.get_chat(chat.id)
            chat_entity.voice_msg_to_text_enabled = True
            chat_entity.save()
            voice: Voice = Voice(bot=chat.bot,
                                 duration=1,
                                 file_id='AwACAgQAAxkBAAIQS2RFXO0thVNH86FUcCwpNK7aHDjUAAJKDgAC7AUgUvVxjAac8EeILwQ',
                                 file_size=30217,
                                 file_unique_id='AgADSg4AAuwFIFI',
                                 mime_type='audio/ogg')

            file: File = File(bot=chat.bot,
                              file_id='AwACAgQAAxkBAAIQS2RFXO0thVNH86FUcCwpNK7aHDjUAAJKDgAC7AUgUvVxjAac8EeILwQ',
                              file_path='https://api.telegram.org/file/bot5057789773:AAGWzH5YYEaSwqDyaJ-Bqg3GgtJ7d1yVVV0/voice/file_1.oga',
                              file_size=30217,
                              file_unique_id='AgADSg4AAuwFIFI')

            voice.get_file = lambda *args, **kwargs: file
            file.download = lambda out, *args, **kwargs: out.write(test_sound_file.read())

            user.send_voice(voice)


def openai_api_mock_response_one_image(*args, **kwargs):
    return OpenAIResponse({'text', 'this is the text content'}, None)


@mock.patch('bobweb.bob.openai_api_utils.user_has_permission_to_use_openai_api', lambda *args: True)
class TranscribeCommandTest(TestCase):
    command_class: ChatCommand.__class__ = TranscribeCommand
    command_str: str = 'tekstitä'

    @classmethod
    def setUpClass(cls) -> None:
        super(TranscribeCommandTest, cls).setUpClass()
        cls.maxDiff = None
        TranscribeCommand.run_async = False

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

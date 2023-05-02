from unittest import mock, skip

import openai
from django.test import TestCase
from openai.openai_response import OpenAIResponse
from requests import Response

from telegram import Voice, File

from bobweb.bob import main, database
from bobweb.bob.command import ChatCommand
from bobweb.bob.command_transcribe import TranscribeCommand
from bobweb.bob.tests_mocks_v2 import init_chat_user
from bobweb.bob.tests_utils import assert_command_triggers, MockResponse


def openai_api_mock_response_with_transcription(*args, **kwargs):
    return MockResponse(status_code=200, text='{"text": "this is mock transcription"}')


class VoiceMessageHandlerTest(TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        super(VoiceMessageHandlerTest, cls).setUpClass()
        cls.maxDiff = None
        openai.api_key = 'api_key_value'

    @skip("Calls real api and should not be run with other tests as this is only created to help with "
          "development and possible debugging")
    @mock.patch('bobweb.bob.openai_api_utils.user_has_permission_to_use_openai_api', lambda *args: True)
    @mock.patch('os.getenv', lambda key: 'DUMMY_VALUE_FOR_ENVIRONMENT_VARIABLE')
    def test_transcribe_audio_file(self):
        """ Development time test that calls real API. Created for faster debugging and testing """
        with open('bobweb/bob/resources/test/telegram_voice_message_mock.ogg', "rb") as test_sound_file:
            chat, user = init_chat_user()
            chat_entity = database.get_chat(chat.id)
            chat_entity.voice_msg_to_text_enabled = True
            chat_entity.save()

            voice: Voice = create_mock_voice(chat.bot, test_sound_file)
            user.send_voice(voice)

    @mock.patch('requests.post', openai_api_mock_response_with_transcription)
    @mock.patch('bobweb.bob.openai_api_utils.user_has_permission_to_use_openai_api', lambda *args: True)
    def test_voice_message_should_be_automatically_transcribed_when_settings_are_accordingly(self):
        """
        Basic tests that covers automatic audio message transcribing while all external calls are mocked.
        """
        with open('bobweb/bob/resources/test/telegram_voice_message_mock.ogg', "rb") as test_sound_file:
            chat, user = init_chat_user()
            chat_entity = database.get_chat(chat.id)
            chat_entity.voice_msg_to_text_enabled = True
            chat_entity.save()

            voice: Voice = create_mock_voice(chat.bot, test_sound_file)
            user.send_voice(voice)

            # Is expecte
            self.assertIn('"<i>this is mock transcription</i>"', chat.last_bot_txt())
            self.assertIn('Rahaa paloi: $0.000100, rahaa palanut rebootin jälkeen: $0.000100', chat.last_bot_txt())


def create_mock_voice(bot, sound_file) -> Voice:
    voice: Voice = Voice(bot=bot,
                         duration=1,
                         file_id='AwACAgQAAxkBAAIQS2RFXO0thVNH86FUcCwpNK7aHDjUAAJKDgAC7AUgUvVxjAac8EeILwQ',
                         file_size=30217,
                         file_unique_id='AgADSg4AAuwFIFI',
                         mime_type='audio/ogg')
    file: File = create_mock_file(bot)
    voice.get_file = lambda *args, **kwargs: file
    file.download = lambda out, *args, **kwargs: out.write(sound_file.read())

    return voice


def create_mock_file(bot) -> File:
    return File(bot=bot,
                file_id='AwACAgQAAxkBAAIQS2RFXO0thVNH86FUcCwpNK7aHDjUAAJKDgAC7AUgUvVxjAac8EeILwQ',
                file_path='https://api.telegram.org/file/bot5057789773:AAGWzH5YYEaSwqDyaJ-Bqg3GgtJ7d1yVVV0/voice/file_1.oga',
                file_size=30217,
                file_unique_id='AgADSg4AAuwFIFI')


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

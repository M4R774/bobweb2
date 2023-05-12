import io
from unittest import mock

import openai
from django.test import TestCase

from telegram import Voice, File

from bobweb.bob import main, database
from bobweb.bob.tests_mocks_v2 import init_chat_user
from bobweb.bob.tests_utils import MockResponse


def openai_api_mock_response_with_transcription(*args, **kwargs):
    return MockResponse(status_code=200, text='{"text": "this is mock transcription"}')


def create_mock_convert_buffer_content_to_audio(written_bytes: int):
    """ Returns mock function that returns empty Bytes object and given
        number as written_bytes buffer size """
    def mock_implementation(*args):
        return io.BytesIO(), written_bytes
    return mock_implementation


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


class VoiceMessageHandlerTest(TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        super(VoiceMessageHandlerTest, cls).setUpClass()
        cls.maxDiff = None
        openai.api_key = 'api_key_value'

    @mock.patch('requests.post', openai_api_mock_response_with_transcription)
    @mock.patch('bobweb.bob.openai_api_utils.user_has_permission_to_use_openai_api', lambda *args: True)
    @mock.patch('bobweb.bob.message_handler_voice.convert_buffer_content_to_audio',
                create_mock_convert_buffer_content_to_audio(12_345))
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

            self.assertIn('"<i>this is mock transcription</i>"', chat.last_bot_txt())
            self.assertIn('Rahaa paloi: $0.000100, rahaa palanut rebootin jälkeen: $0.000100', chat.last_bot_txt())


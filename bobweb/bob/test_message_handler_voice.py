from unittest import mock
from django.test import TestCase
from unittest.mock import Mock

from telegram import Update, Voice, File

from bobweb.bob import message_handler_voice, database
from bobweb.bob.tests_mocks_v2 import MockChat, MockMessage, MockUser, init_chat_user


class VoiceMessageHandlerTest(TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super(VoiceMessageHandlerTest, cls).setUpClass()
        cls.maxDiff = None

    @mock.patch('bobweb.bob.openai_api_utils.user_has_permission_to_use_openai_api', lambda *args: True)
    @mock.patch('os.getenv', lambda key: 'DUMMY_VALUE_FOR_ENVIRONMENT_VARIABLE')
    def test_transcribe_audio_file(self):
        """ Development time test that calls real API """
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



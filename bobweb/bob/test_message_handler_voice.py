from unittest import mock
from django.test import TestCase
from unittest.mock import Mock

from telegram import Update, Voice, File

from bobweb.bob import main, database, command_service
from bobweb.bob.activities.activity_state import ActivityState
from bobweb.bob.activities.command_activity import CommandActivity
from bobweb.bob.message_handler_voice import create_page_labels, ContentPaginationState
from bobweb.bob.tests_mocks_v2 import init_chat_user
from bobweb.bob.tests_msg_btn_utils import button_labels_from_reply_markup
from bobweb.bob.utils_common import split_text


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


class TestPagination(TestCase):

    def test_simple_cases_with_incresing_page_count(self):
        self.assertEqual(['[1]'], create_page_labels(1, 0))
        self.assertEqual(['[1]', '2'], create_page_labels(2, 0))
        self.assertEqual(['[1]', '2', '3', '4', '5'], create_page_labels(5, 0))
        self.assertEqual(['[1]', '2', '3', '4', '5', '6', '7'], create_page_labels(7, 0))
        self.assertEqual(['[1]', '2', '3', '4', '5', '6', '>>'], create_page_labels(10, 0))

    def test_current_page_is_always_surrounded_with_brackets(self):
        self.assertEqual(['[1]', '2', '3', '4', '5', '6', '>>'], create_page_labels(10, 0))
        self.assertEqual(['1', '[2]', '3', '4', '5', '6', '>>'], create_page_labels(10, 1))
        self.assertEqual(['1', '2', '[3]', '4', '5', '6', '>>'], create_page_labels(10, 2))
        self.assertEqual(['1', '2', '3', '[4]', '5', '6', '>>'], create_page_labels(10, 3))

    def test_current_page_is_kept_centered_when_possible(self):
        self.assertEqual(['1', '2', '[3]', '4', '5', '6', '>>'], create_page_labels(10, 2))
        self.assertEqual(['1', '2', '3', '[4]', '5', '6', '>>'], create_page_labels(10, 3))
        self.assertEqual(['<<', '3', '4', '[5]', '6', '7', '>>'], create_page_labels(10, 4))
        self.assertEqual(['<<', '4', '5', '[6]', '7', '8', '>>'], create_page_labels(10, 5))
        self.assertEqual(['<<', '5', '6', '[7]', '8', '9', '10'], create_page_labels(10, 6))
        self.assertEqual(['<<', '5', '6', '7', '[8]', '9', '10'], create_page_labels(10, 7))
        self.assertEqual(['<<', '5', '6', '7', '8', '[9]', '10'], create_page_labels(10, 8))
        self.assertEqual(['<<', '5', '6', '7', '8', '9', '[10]'], create_page_labels(10, 9))


    def test_paginated_message_content(self):
        # Setup content for the paged
        pages = split_text('Mary had a little lamb and it was called Daisy', 20)
        self.assertEqual(['Mary had a little', 'lamb and it was', 'called Daisy'], pages)

        # Create state and use mock message handler while sending single message that just starts the activity
        state = ContentPaginationState(pages)
        with mock.patch('bobweb.bob.message_handler.handle_update', mock_activity_starter(state)):
            chat, user = init_chat_user()
            user.send_message('paginate that')

            # Now assert that the content is as expected. Should have header with page information and labels that show
            # current page and other pages
            self.assertEqual('[Sivu (1 / 3)]\nMary had a little', chat.last_bot_txt())
            labels = button_labels_from_reply_markup(chat.last_bot_msg().reply_markup)
            self.assertEqual(['[1]', '2', '3'], labels)

            # Change page and assert content has updated as expected
            user.press_button_with_text('2', chat.last_bot_msg())

            self.assertEqual('[Sivu (2 / 3)]\nlamb and it was', chat.last_bot_txt())
            labels = button_labels_from_reply_markup(chat.last_bot_msg().reply_markup)
            self.assertEqual(['1', '[2]', '3'], labels)

    def test_skip_to_end_and_skip_to_start_work_as_expected(self):
        pages = ['1', '2', '3', '4', '5', '6', '7', '8', '9', '10']

        state = ContentPaginationState(pages)
        with mock.patch('bobweb.bob.message_handler.handle_update', mock_activity_starter(state)):
            chat, user = init_chat_user()
            user.send_message('paginate that')
            user.press_button_with_text('5', chat.last_bot_msg())

            self.assertEqual('[Sivu (5 / 10)]\n5', chat.last_bot_txt())
            labels = button_labels_from_reply_markup(chat.last_bot_msg().reply_markup)
            self.assertEqual(['<<', '3', '4', '[5]', '6', '7', '>>'], labels)

            # Now, pressing skip to end should change page to 10
            user.press_button_with_text('>>', chat.last_bot_msg())
            self.assertEqual('[Sivu (10 / 10)]\n10', chat.last_bot_txt())

            # And pressing skip to start should change page to 1
            user.press_button_with_text('<<', chat.last_bot_msg())
            self.assertEqual('[Sivu (1 / 10)]\n1', chat.last_bot_txt())


def mock_activity_starter(initial_state: ActivityState) -> callable:
    """ Can be used to mock MessageHandler that just creates activity with given state for each message """
    def mock_message_handler(update, context):
        activity = CommandActivity(initial_update=update, state=initial_state)
        command_service.instance.add_activity(activity)
    return mock_message_handler

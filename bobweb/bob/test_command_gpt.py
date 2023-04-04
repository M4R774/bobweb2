import os
from typing import Tuple

from django.test import TestCase
from unittest import mock
from unittest.mock import patch

from bobweb.bob import database, command_gpt
from bobweb.bob.tests_mocks_v2 import init_chat_user, MockChat, MockUser
from bobweb.bob.tests_utils import assert_reply_equal, \
    assert_get_parameters_returns_expected_value, \
    assert_command_triggers

from bobweb.bob.command_gpt import GptCommand

import django

from bobweb.web.bobapp.models import TelegramUser

os.environ.setdefault(
    'DJANGO_SETTINGS_MODULE',
    'bobweb.web.web.settings'
)

os.environ['DJANGO_ALLOW_ASYNC_UNSAFE'] = 'true'
django.setup()


class MockOpenAIObject:
    def __init__(self):
        self.choices = [self.Choice()]
        self.usage = self.Usage()

    class Choice:
        def __init__(self):
            self.message = self.Message()

        class Message:
            def __init__(self):
                self.content = 'The Los Angeles Dodgers won the World Series in 2020.'
                self.role = 'assistant'

    class Usage:
        def __init__(self):
            self.total_tokens = 42


def mock_response_from_openai(*args, **kwargs):
    return MockOpenAIObject()


# Single instance to serve all tests that need instance of GptCommand
gpt_command = command_gpt.instance

cc_holder_id = 1337  # Credit card holder id
mock_chat_v1_id = 1337  # Default chat id for tests using MockChat v1


@mock.patch('os.getenv', lambda key: 'DUMMY_VALUE_FOR_ENVIRONMENT_VARIABLE')
@mock.patch('openai.ChatCompletion.create', mock_response_from_openai)
class ChatGptCommandTests(TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        super(ChatGptCommandTests, cls).setUpClass()
        os.system('python bobweb/web/manage.py migrate')
        GptCommand.run_async = False
        telegram_user = database.get_telegram_user(cc_holder_id)
        database.set_credit_card_holder(telegram_user)

    def test_command_triggers(self):
        should_trigger = ['/gpt', '!gpt', '.gpt', '/GPT', '/gpt test']
        should_not_trigger = ['gpt', 'test /gpt', '/gpt4 test']
        assert_command_triggers(self, GptCommand, should_trigger, should_not_trigger)

    def test_user_has_permission_if_credit_card_holder_in_same_chat(self):
        self.assertEqual(database.get_credit_card_holder().id, cc_holder_id)
        chat = database.get_chat(-666)
        database.increment_chat_member_message_count(chat_id=-666, user_id=cc_holder_id)
        self.assertTrue(gpt_command.is_enabled_in(chat))

    def test_user_that_dos_not_share_group_with_cc_holder_has_no_permission(self):
        """ Just a new chat and new user. Has no common chats with current cc_holder so should not have permission
            to use gpt-command """
        chat, user = init_chat_user()
        self.assertNotEqual(user.id, cc_holder_id)
        user.send_message('/gpt this should give error')
        self.assertIn('Komennon käyttö on rajattu pienelle testiryhmälle käyttäjiä', chat.last_bot_txt())

    def test_any_user_in_same_chat_as_cc_holder_has_permission(self):
        """ Create new chat and add cc_holder and another user to that chat. Now another user has permission
            to use gpt-command """
        chat, cc_holder, other_user = init_chat_with_bot_cc_holder_and_another_user()

        self.assertEqual(cc_holder.id, database.get_credit_card_holder().id)

        # Now as user_a and cc_holder are in the same chat, user_a has permission to use command
        other_user.send_message('/gpt this should return gpt-message')
        self.assertIn('The Los Angeles Dodgers won the World Series in 2020.', chat.last_bot_txt())

    def test_any_user_having_any_common_group_with_cc_holder_has_permission_to_use_command_in_any_group(self):
        """ Demonstrates, that if user has any common chat with credit card holder, they have permission to
            use command in any other chat (including private chats)"""
        chat, cc_holder, other_user = init_chat_with_bot_cc_holder_and_another_user()

        # Now, for other user create a new chat and send message in there
        new_chat = MockChat(type='private')
        other_user.send_message('/gpt new message to new chat', chat=new_chat)
        self.assertIn('The Los Angeles Dodgers won the World Series in 2020.', new_chat.last_bot_txt())

    def test_no_prompt_gives_help_reply(self):
        assert_reply_equal(self, '/gpt', "Anna jokin syöte komennon jälkeen. '[.!/]gpt [syöte]'")

    def test_get_given_parameter(self):
        assert_get_parameters_returns_expected_value(self, '!gpt', gpt_command)

    def test_should_contain_correct_response(self):
        gpt_command.costs_so_far = 0
        assert_reply_equal(self, '/gpt Who won the world series in 2020?',
                           'The Los Angeles Dodgers won the World Series in 2020.'
                           '\n\nRahaa paloi: $0.000084, rahaa palanut rebootin jälkeen: $0.000084')

    def test_set_new_system_prompt(self):
        assert_reply_equal(self, '.gpt .system uusi homma', 'Uusi system-viesti on nyt:\n\nuusi homma')

    def test_setting_context_limit(self):
        gpt_command.conversation_context = {}
        gpt_command.costs_so_far = 0
        self.assertEqual(0, len(gpt_command.conversation_context))
        for i in range(25):
            assert_reply_equal(self, '.gpt Konteksti ' + str(i), "The Los Angeles Dodgers won the World Series in 2020."
                               "\n\nRahaa paloi: $0.000084, rahaa palanut rebootin jälkeen: $"
                               + "{:f}".format((i+1)*0.000084))
        self.assertEqual(20, len(gpt_command.conversation_context.get(mock_chat_v1_id)))

    def test_context_content(self):
        gpt_command.conversation_context = {}
        gpt_command.costs_so_far = 0
        self.assertEqual(0, len(gpt_command.conversation_context))
        assert_reply_equal(self, '.gpt .system uusi homma', 'Uusi system-viesti on nyt:\n\nuusi homma')
        for i in range(25):
            assert_reply_equal(self, '.gpt Konteksti ' + str(i),
                               "The Los Angeles Dodgers won the World Series in 2020."
                               "\n\nRahaa paloi: $0.000084, rahaa palanut rebootin jälkeen: $"
                               + "{:f}".format((i+1)*0.000084))
        self.assertEqual([{'content': 'uusi homma', 'role': 'system'},
                         {'content': 'Konteksti 15', 'role': 'user'},
                         {'content': 'The Los Angeles Dodgers won the World Series in 2020.',
                          'role': 'assistant'},
                         {'content': 'Konteksti 16', 'role': 'user'},
                         {'content': 'The Los Angeles Dodgers won the World Series in 2020.',
                          'role': 'assistant'},
                         {'content': 'Konteksti 17', 'role': 'user'},
                         {'content': 'The Los Angeles Dodgers won the World Series in 2020.',
                          'role': 'assistant'},
                         {'content': 'Konteksti 18', 'role': 'user'},
                         {'content': 'The Los Angeles Dodgers won the World Series in 2020.',
                          'role': 'assistant'},
                         {'content': 'Konteksti 19', 'role': 'user'},
                         {'content': 'The Los Angeles Dodgers won the World Series in 2020.',
                          'role': 'assistant'},
                         {'content': 'Konteksti 20', 'role': 'user'},
                         {'content': 'The Los Angeles Dodgers won the World Series in 2020.',
                          'role': 'assistant'},
                         {'content': 'Konteksti 21', 'role': 'user'},
                         {'content': 'The Los Angeles Dodgers won the World Series in 2020.',
                          'role': 'assistant'},
                         {'content': 'Konteksti 22', 'role': 'user'},
                         {'content': 'The Los Angeles Dodgers won the World Series in 2020.',
                          'role': 'assistant'},
                         {'content': 'Konteksti 23', 'role': 'user'},
                         {'content': 'The Los Angeles Dodgers won the World Series in 2020.',
                          'role': 'assistant'},
                         {'content': 'Konteksti 24', 'role': 'user'},
                         {'content': 'The Los Angeles Dodgers won the World Series in 2020.',
                          'role': 'assistant'}],
                         gpt_command.build_message(mock_chat_v1_id))

    def test_context_content_is_chat_specific(self):
        # Initiate 2 different chats that have cc-holder as member
        # cc-holder user is ignored as it's not needed in this test case
        chat_a, _, user_a = init_chat_with_bot_cc_holder_and_another_user()
        chat_b, _, user_b = init_chat_with_bot_cc_holder_and_another_user()

        # Both users send message with gpt command to their corresponding chats
        user_a.send_message('/gpt this is chat a', chat=chat_a)
        user_b.send_message('/gpt 🅱️', chat=chat_b)

        # Assert, that each chat's context contains expected value
        self.assertEqual('this is chat a', gpt_command.conversation_context.get(chat_a.id)[0]['content'])
        self.assertEqual('🅱️', gpt_command.conversation_context.get(chat_b.id)[0]['content'])

def init_chat_with_bot_cc_holder_and_another_user() -> Tuple[MockChat, MockUser, MockUser]:
    """
    Initiate chat and 2 users. One is cc_holder and other is not
    :return: chat: MockChat, cc_holder_user: MockUser, other_user: MockUser
    """
    chat = MockChat()
    user_a = MockUser(chat=chat)
    user_cc_holder = MockUser(id=cc_holder_id, chat=chat)
    # Send messages for both to perist chat and users to database
    user_a.send_message('hi')
    user_cc_holder.send_message('greetings')

    return chat, user_cc_holder, user_a

import os
from typing import Tuple

from django.test import TestCase
from unittest import mock

from bobweb.bob import database, command_gpt
from bobweb.bob.tests_mocks_v2 import init_chat_user, MockChat, MockUser

from bobweb.bob.command_gpt import GptCommand, no_parameters_given_notification_msg

import django

from bobweb.bob.tests_utils import assert_command_triggers, assert_get_parameters_returns_expected_value
from bobweb.web.bobapp.models import Chat

os.environ.setdefault(
    'DJANGO_SETTINGS_MODULE',
    'bobweb.web.web.settings'
)

os.environ['DJANGO_ALLOW_ASYNC_UNSAFE'] = 'true'
django.setup()


class MockOpenAIObject:
    def __init__(self):
        self.choices = [Choice()]
        self.usage = Usage()


class Choice:
    def __init__(self):
        self.message = Message()


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

    def test_get_given_parameter(self):
        assert_get_parameters_returns_expected_value(self, '!gpt', gpt_command)

    def test_no_prompt_gives_help_reply(self):
        chat, _, user = init_chat_with_bot_cc_holder_and_another_user()
        user.send_message('/gpt')
        self.assertEqual(no_parameters_given_notification_msg, chat.last_bot_txt())

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

    def test_should_contain_correct_response(self):
        gpt_command.costs_so_far = 0
        chat, _, user = init_chat_with_bot_cc_holder_and_another_user()
        user.send_message('/gpt Who won the world series in 2020?')
        expected_reply = 'The Los Angeles Dodgers won the World Series in 2020.' \
                         '\n\nRahaa paloi: $0.000084, rahaa palanut rebootin jälkeen: $0.000084'
        self.assertEqual(expected_reply, chat.last_bot_txt())

    def test_set_new_system_prompt(self):
        chat, _, user = init_chat_with_bot_cc_holder_and_another_user()
        user.send_message('.gpt .system uusi homma')
        self.assertEqual('Uusi system-viesti on nyt:\n\nuusi homma', chat.last_bot_txt())

    def test_setting_context_limit(self):
        gpt_command.costs_so_far = 0
        chat, _, user = init_chat_with_bot_cc_holder_and_another_user()
        for i in range(25):
            user.send_message(f'.gpt Konteksti {i}')
            self.assertIn(f"Rahaa paloi: $0.000084, rahaa palanut rebootin jälkeen: ${get_cost_str(i+1)}",
                          chat.last_bot_txt())

        self.assertEqual(20, len(gpt_command.conversation_context.get(chat.id)))

    def test_context_content(self):
        gpt_command.costs_so_far = 0
        chat, _, user = init_chat_with_bot_cc_holder_and_another_user()
        user.send_message('.gpt .system uusi homma')
        self.assertEqual('Uusi system-viesti on nyt:\n\nuusi homma', chat.last_bot_txt())
        for i in range(25):
            user.send_message(f'.gpt Konteksti {i}')
            self.assertIn(f"Rahaa paloi: $0.000084, rahaa palanut rebootin jälkeen: ${get_cost_str(i+1)}",
                          chat.last_bot_txt())

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
                         gpt_command.build_message(chat.id))

    def test_context_content_is_chat_specific(self):
        # Initiate 2 different chats that have cc-holder as member
        # cc-holder user is ignored as it's not needed in this test case
        chat_a, _, user_a = init_chat_with_bot_cc_holder_and_another_user()
        b_chat, _, b_user = init_chat_with_bot_cc_holder_and_another_user()

        # Both users send message with gpt command to their corresponding chats
        user_a.send_message('/gpt this is chat a')
        b_user.send_message('/gpt 🅱️')

        # Assert, that each chat's context contains expected value
        self.assertEqual('this is chat a', gpt_command.conversation_context.get(chat_a.id)[0]['content'])
        self.assertEqual('🅱️', gpt_command.conversation_context.get(b_chat.id)[0]['content'])

    def test_chat_context_can_be_emptied_and_empty_is_chat_specific(self):
        chat_a, _, user_a = init_chat_with_bot_cc_holder_and_another_user()
        b_chat, _, b_user = init_chat_with_bot_cc_holder_and_another_user()

        # Both users send message with gpt command to their corresponding chats
        user_a.send_message('/gpt this is chat a')
        b_user.send_message('/gpt 🅱️')

        self.assertEqual('this is chat a', gpt_command.conversation_context.get(chat_a.id)[0]['content'])
        self.assertEqual('🅱️', gpt_command.conversation_context.get(b_chat.id)[0]['content'])

        # Now empty one, the other should still contain context
        user_a.send_message('/gpt /reset')
        self.assertEqual([], gpt_command.conversation_context.get(chat_a.id))
        self.assertEqual('🅱️', gpt_command.conversation_context.get(b_chat.id)[0]['content'])

        # Empty other as well and now both should be empty
        b_user.send_message('/gpt /reset')
        self.assertEqual([], gpt_command.conversation_context.get(chat_a.id))
        self.assertEqual([], gpt_command.conversation_context.get(b_chat.id))

    def test_prints_system_prompt_if_sub_command_given_without_parameters(self):
        # Create a new chat. Expect bot to tell, that system msg is empty
        chat, _, user = init_chat_with_bot_cc_holder_and_another_user()
        user.send_message('/gpt /system')
        self.assertIn('Nykyinen system-viesti on nyt tyhjä', chat.last_bot_txt())

        # Now set system message for chat and check that it is contained in the response
        chat_entity = Chat.objects.get(id=chat.id)
        chat_entity.gpt_system_prompt = '_system_prompt_'
        chat_entity.save()

        user.send_message('/gpt /system')
        self.assertIn('Nykyinen system-viesti on nyt:\n\n_system_prompt_', chat.last_bot_txt())

    def test_system_prompt_can_be_updated_with_sub_command(self):
        # Create a new chat. Expect bot to tell, that system msg is empty
        chat, _, user = init_chat_with_bot_cc_holder_and_another_user()
        user.send_message('/gpt /system')
        self.assertIn('Nykyinen system-viesti on nyt tyhjä', chat.last_bot_txt())

        # Give command to update system message, check from database that it has been updated
        user.send_message('/gpt /system _new_system_prompt_')

        chat_entity = Chat.objects.get(id=chat.id)
        self.assertEqual('_new_system_prompt_', chat_entity.gpt_system_prompt)

    def test_system_prompt_is_chat_specific(self):
        # Initiate 2 different chats that have cc-holder as member
        # cc-holder user is ignored as it's not needed in this test case
        chat_a, _, user_a = init_chat_with_bot_cc_holder_and_another_user()
        b_chat, _, b_user = init_chat_with_bot_cc_holder_and_another_user()

        # Both users send message with gpt command to their corresponding chats
        user_a.send_message('/gpt /system')
        b_user.send_message('/gpt /system')

        self.assertIn('Nykyinen system-viesti on nyt tyhjä', chat_a.last_bot_txt())
        self.assertIn('Nykyinen system-viesti on nyt tyhjä', b_chat.last_bot_txt())

        # Update chat a system message and check that it has changed in the database, but chat b has not
        user_a.send_message('/gpt /system AAA')
        self.assertEqual('AAA', Chat.objects.get(id=chat_a.id).gpt_system_prompt)
        self.assertIsNone(Chat.objects.get(id=b_chat.id).gpt_system_prompt)

        # Update chat b system message and check that it has changed in the database
        b_user.send_message('/gpt /system 🅱️')
        self.assertEqual('AAA', Chat.objects.get(id=chat_a.id).gpt_system_prompt)
        self.assertEqual('🅱️', Chat.objects.get(id=b_chat.id).gpt_system_prompt)


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


def get_cost_str(prompt_count: int) -> str:
    return format_money(prompt_count*0.000084)


def format_money(money: float) -> str:
    return '{:f}'.format(money)

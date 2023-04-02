import os

from unittest import IsolatedAsyncioTestCase, mock
from unittest.mock import patch

from bobweb.bob import database, command_service
from bobweb.bob.tests_mocks_v1 import MockUser, MockChat
from bobweb.bob.tests_utils import assert_reply_equal, \
    assert_get_parameters_returns_expected_value, \
    assert_command_triggers, assert_reply_to_contain

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


@mock.patch('os.getenv', lambda key: 'DUMMY_VALUE_FOR_ENVIRONMENT_VARIABLE')
@mock.patch('openai.ChatCompletion.create', mock_response_from_openai)
class Test(IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        os.system('python bobweb/web/manage.py migrate')
        GptCommand.run_async = False
        mock_user = MockUser()
        telegram_user = TelegramUser(id=mock_user.id)
        database.set_credit_card_holder(telegram_user)

    def test_is_enabled_in(self):
        self.assertEqual(database.get_credit_card_holder().id, 1337)
        chat = database.get_chat(-666)
        database.increment_chat_member_message_count(chat_id=-666, user_id=1337)
        self.assertTrue(GptCommand().is_enabled_in(chat))

    def test_no_prompt_gives_help_reply(self):
        GptCommand.costs_so_far = 0
        assert_reply_equal(self, '/gpt', "Anna jokin syöte komennon jälkeen. '[.!/]gpt [syöte]'")

    def test_get_given_parameter(self):
        assert_get_parameters_returns_expected_value(self, '!gpt', GptCommand())

    def test_should_contain_correct_response(self):
        GptCommand.costs_so_far = 0
        assert_reply_equal(self, '/gpt Who won the world series in 2020?',
                           'The Los Angeles Dodgers won the World Series in 2020.'
                           '\n\nRahaa paloi: $0.000084, rahaa palanut rebootin jälkeen: $0.000084')

    def test_set_new_system_prompt(self):
        assert_reply_equal(self, '.gpt .system uusi homma', 'Uusi system-viesti on nyt:\n\nuusi homma')

    def test_setting_context_limit(self):
        GptCommand.conversation_context = []
        self.assertEqual(0, len(GptCommand.conversation_context))
        for i in range(25):
            assert_reply_equal(self, '.gpt Konteksti ' + str(i), "The Los Angeles Dodgers won the World Series in 2020."
                               "\n\nRahaa paloi: $0.000084, rahaa palanut rebootin jälkeen: $"
                               + "{:f}".format((i+1)*0.000084))
        self.assertEqual(20, len(GptCommand.conversation_context))

    def test_context_content(self):
        GptCommand.conversation_context = []
        self.assertEqual(0, len(GptCommand.conversation_context))
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
                         GptCommand().build_message())

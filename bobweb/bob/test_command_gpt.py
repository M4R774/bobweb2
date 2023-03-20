import os

from unittest import IsolatedAsyncioTestCase, mock
from unittest.mock import patch

from bobweb.bob import database
from bobweb.bob.tests_mocks_v1 import MockUser
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

    def test_no_prompt_gives_normal_reply(self):
        assert_reply_equal(self, '/gpt', "The Los Angeles Dodgers won the World Series in 2020.\n\nRahaa paloi: $0.000084, rahaa palanut rebootin jälkeen: $0.000084")

    def test_get_given_parameter(self):
        assert_get_parameters_returns_expected_value(self, '!gpt', GptCommand())

    def test_should_contain_correct_response(self):
        assert_reply_equal(self, '/gpt Who won the world series in 2020?', 'The Los Angeles Dodgers won the World Series in 2020.\n\nRahaa paloi: $0.000084, rahaa palanut rebootin jälkeen: $0.000168')

    def test_set_new_system_prompt(self):
        assert_reply_equal(self, '.gpt .system uusi homma', 'Uusi system-viesti on nyt:\n\nuusi homma')

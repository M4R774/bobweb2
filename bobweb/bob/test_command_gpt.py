import os

from unittest import IsolatedAsyncioTestCase, mock
from unittest.mock import patch

from bobweb.bob.tests_utils import assert_reply_equal, \
    assert_get_parameters_returns_expected_value, \
    assert_command_triggers, assert_reply_to_contain

from bobweb.bob.command_gpt import GptCommand

import django

os.environ.setdefault(
    'DJANGO_SETTINGS_MODULE',
    'bobweb.web.web.settings'
)

os.environ['DJANGO_ALLOW_ASYNC_UNSAFE'] = 'true'
django.setup()


class MockOpenAIObject:
    def __init__(self):
        self.choices = [self.Choice()]

    class Choice():
        def __init__(self):
            self.message = self.Message()

        class Message():
            def __init__(self):
                self.content = 'The Los Angeles Dodgers won the World Series in 2020.'
                self.role = 'assistant'


def mock_response_from_openai(*args, **kwargs):
    return MockOpenAIObject()


@mock.patch('os.getenv', lambda key: 'DUMMY_VALUE_FOR_ENVIRONMENT_VARIABLE')
@mock.patch('openai.ChatCompletion.create', mock_response_from_openai)
class Test(IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        os.system('python bobweb/web/manage.py migrate')
        GptCommand.run_async = False

    def test_command_triggers(self):
        should_trigger = ['/gpt', '!gpt', '.gpt', '/GPT', '/gpt test']
        should_not_trigger = ['gpt', 'test /gpt']
        assert_command_triggers(self, GptCommand, should_trigger, should_not_trigger)

    def test_no_prompt_gives_help_reply(self):
        assert_reply_equal(self, '/gpt', "Anna jokin syöte komennon jälkeen. '[.!/]gpt [syöte]'")

    def test_get_given_parameter(self):
        assert_get_parameters_returns_expected_value(self, '!gpt', GptCommand())

    def test_should_contain_correct_response(self):
        assert_reply_to_contain(self, '/gpt Who won the world series in 2020?', ['The Los Angeles Dodgers won the World Series in 2020.'])

import os
import string
from typing import List
from unittest import TestCase

import django
import pytz
from telegram import ReplyMarkup

from bobweb.bob import command_service
from bobweb.bob.command import ChatCommand
from bobweb.bob.tests_mocks_v1 import MockUpdate, MockChatMember
from bobweb.bob.utils_common import has

os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    "bobweb.web.web.settings"
)
os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"
django.setup()


# Bob should reply anything to given message
def assert_has_reply_to(test: TestCase, message_text: string):
    update = MockUpdate().send_text(message_text)
    reply = update.effective_message.reply_message_text
    test.assertIsNotNone(reply)


# Bob should not reply to given message
def assert_no_reply_to(test: TestCase, message_text: string):
    update = MockUpdate().send_text(message_text)
    reply = update.effective_message.reply_message_text
    test.assertIsNone(reply)


# Bobs message should contain all given elements in the list
def assert_reply_to_contain(test: TestCase, message_text: string, expected_list: List[str]):
    update = MockUpdate().send_text(message_text)
    assert_message_contains(test, update.effective_message, expected_list)


def assert_message_contains(test: TestCase, message: 'MockMessage', expected_list: List[str]):
    reply = message.reply_message_text
    test.assertIsNotNone(reply)
    for expected in expected_list:
        test.assertRegex(reply, expected)


# Bobs message should contain all given elements in the list
def assert_reply_to_not_contain(test: TestCase, message_text: string, expected_list: List[type(string)]):
    update = MockUpdate().send_text(message_text)
    reply = update.effective_message.reply_message_text
    test.assertIsNotNone(reply)
    for expected in expected_list:
        test.assertNotRegex(reply, expected)


# Reply should be strictly equal to expected text
def assert_reply_equal(test: TestCase, message_text: string, expected: string):
    update = MockUpdate().send_text(message_text)
    test.assertEqual(expected, update.effective_message.reply_message_text)


# Test Command.get_parameters(message) for given command
def assert_get_parameters_returns_expected_value(test: TestCase, command_text: str, command: ChatCommand):
    message = f'{command_text} test . test/test-test\ntest\ttest .vai test \n '
    parameter_expected = 'test . test/test-test\ntest\ttest .vai test'
    parameter_actual = command.get_parameters(message)
    test.assertEqual(parameter_expected, parameter_actual)


def get_latest_active_activity():
    activities = command_service.instance.current_activities
    if has(activities):
        return activities[len(activities) - 1]

#
# Daily Question test utils
#
def buttons_from_reply_markup(reply_markup: ReplyMarkup) -> List[dict]:
    keyboard = reply_markup.to_dict().get('inline_keyboard')
    button_array = keyboard[0]
    return [button for button in button_array]


def button_labels_from_reply_markup(reply_markup: ReplyMarkup) -> List[str]:
    buttons = buttons_from_reply_markup(reply_markup)
    return [button.get('text') for button in buttons]


def get_callback_data_from_buttons_by_text(buttons: List[dict], text: str) -> str:
    # get the callback_data from object in the list if it's text attribute contains given text
    return next((x['callback_data'] for x in buttons if text.lower() in x['text'].lower()), None)


def always_last_choice(values):
    return values[-1]


class MockResponse:
    def __init__(self, status_code=0, content=''):
        self.status_code = status_code
        self.content = content

    def json(self):
        return self.content


def mock_get_chat_member(*args, **kwargs) -> MockChatMember:
    return MockChatMember(*args, **kwargs)


# Can be used as a mock for example with '@mock.patch('requests.post', mock_request_200)'
def mock_response_200(*args, **kwargs) -> MockResponse:
    del args, kwargs
    return MockResponse(status_code=200, content='test')


# Returns a lambda function that when called returns mock response with given status code
# Example usage: 'with mock.patch('requests.post', mock_response_with_code(404))'
def mock_response_with_code(status_code=0, content=''):
    return lambda *args, **kwargs: MockResponse(status_code=status_code, content=content)

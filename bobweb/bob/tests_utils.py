import os
import string
import time
from typing import List, Type
from unittest.mock import patch

from django.test import TestCase

import django

from bobweb.bob import command_service
from bobweb.bob.command import ChatCommand, chat_command_class_type
from bobweb.bob.tests_mocks_v1 import MockUpdate
from bobweb.bob.tests_mocks_v2 import init_chat_user
from bobweb.bob.utils_common import has

os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    "bobweb.web.web.settings"
)
os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"
django.setup()


def assert_command_triggers(test: TestCase,
                            command_class: Type[chat_command_class_type],
                            should_trigger: List[str],
                            should_not_trigger: List[str]) -> None:
    """
    Tests that given command's 'handle_message' is triggered as expected. Actual implementation of
    'handle_message' is replaces with mock so no need to mock anything from the implementation.

    :param test: testCase from which assert method is called
    :param command_class: any subclass of ChatCommand. Patches the 'handle_update' method from the given class
    :param should_trigger: List of message texts that when sent to a chat should trigger the given command
    :param should_not_trigger: List of message texts that when sent to a chat should NOT trigger the given command
    :return: None - calls test assertions
    """
    chat, user = init_chat_user()
    # patch.object: Easy way to replace a class method with a predefined or plain Mock object
    # More info: #https://docs.python.org/3/library/unittest.mock.html#patch-object
    with patch.object(command_class, command_class.handle_update.__name__) as mock_handler:
        # Test all expected message contents to trigger handler as expected
        for i, msg_text in enumerate(should_trigger):
            user.send_message(msg_text)
            fail_msg = command_should_trigger_fail_msg_template.format(msg_text, i)
            test.assertEqual(i + 1, mock_handler.call_count, fail_msg)

        # Test that none of 'should_not_trigger' messages do not trigger
        should_trigger_length = len(should_trigger)
        for i, msg_text in enumerate(should_not_trigger):
            user.send_message(msg_text)
            fail_msg = command_should_not_trigger_fail_msg_template.format(msg_text, i)
            test.assertEqual(should_trigger_length, mock_handler.call_count, fail_msg)


command_should_trigger_fail_msg_template = \
    '\nMessage with content: \'{}\' at index: {} of given \'should_trigger\' list did not trigger ' \
    'command\'s handler.\nExpected behavior: message_handler should be called for this message'

command_should_not_trigger_fail_msg_template = \
    '\nMessage with content: \'{}\' at index: {} of given \'should_not_trigger\' list did trigger ' \
    'command\'s handler.\nExpected behavior: message_handler should not be called for this message'


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
def assert_reply_to_not_contain(test: TestCase, message_text: str, expected_list: List[type(str)]):
    update = MockUpdate().send_text(message_text)
    reply = update.effective_message.reply_message_text
    test.assertIsNotNone(reply)
    for expected in expected_list:
        test.assertNotRegex(reply, expected)


# Reply should be strictly equal to expected text
def assert_reply_equal(test: TestCase, message_text: str, expected: str):
    update = MockUpdate().send_text(message_text)
    test.assertEqual(expected, update.effective_message.reply_message_text)


def assert_get_parameters_returns_expected_value(test: TestCase, command_text: str, command: ChatCommand):
    """ Test Command.get_parameters(message) for given command """
    # Case 1: has parameter
    message = f'{command_text} test . test/test-test\ntest\ttest .vai test \n '
    parameter_expected = 'test . test/test-test\ntest\ttest .vai test'
    parameter_actual = command.get_parameters(message)
    test.assertEqual(parameter_expected, parameter_actual)

    # Case 2: does not have parameter
    message = f'{command_text}'
    test.assertEqual('', command.get_parameters(message))



def get_latest_active_activity():
    activities = command_service.instance.current_activities
    if has(activities):
        return activities[len(activities) - 1]


def always_last_choice(values):
    return values[-1]


class MockResponse:
    def __init__(self, status_code=0, content=''):
        self.status_code = status_code
        self.content = content

    def json(self):
        return self.content


# Can be used as a mock for example with '@mock.patch('requests.post', mock_request_200)'
def mock_response_200(*args, **kwargs) -> MockResponse:
    del args, kwargs
    return MockResponse(status_code=200, content='test')


# Returns a lambda function that when called returns mock response with given status code
# Example usage: 'with mock.patch('requests.post', mock_response_with_code(404))'
def mock_response_with_code(status_code=0, content=''):
    return lambda *args, **kwargs: MockResponse(status_code=status_code, content=content)


def mock_random_with_delay(values):
    time.sleep(0.05)
    return values[0]

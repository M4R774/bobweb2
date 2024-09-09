import json
import os
import string
from typing import List
from unittest import mock
from unittest.mock import patch

from aiohttp import ClientResponseError, RequestInfo
from django.test import TestCase

import django
from httpcore import URL

from bobweb.bob import command_service
from bobweb.bob.command import ChatCommand
from bobweb.bob.tests_mocks_v2 import init_chat_user
from bobweb.bob.utils_common import has

os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    "bobweb.web.web.settings"
)
os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"
django.setup()


# Mock implementation for patching asyncio.sleep with implementation that does nothing
class AsyncMock(mock.MagicMock):
    async def __call__(self, *args, **kwargs):
        return super(AsyncMock, self).__call__(*args, **kwargs)


# Async mock that raises an exception
class AsyncMockRaises(mock.MagicMock):
    def __init__(self, exception: Exception, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.exception = exception

    async def __call__(self, *args, **kwargs):
        raise self.exception


async def assert_command_triggers(test: TestCase,
                                  command_class: ChatCommand.__class__,
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
            await user.send_message(msg_text)
            fail_msg = command_should_trigger_fail_msg_template.format(msg_text, i)
            test.assertEqual(i + 1, mock_handler.call_count, fail_msg)

        # Test that none of 'should_not_trigger' messages do not trigger
        should_trigger_length = len(should_trigger)
        for i, msg_text in enumerate(should_not_trigger):
            await user.send_message(msg_text)
            fail_msg = command_should_not_trigger_fail_msg_template.format(msg_text, i)
            test.assertEqual(should_trigger_length, mock_handler.call_count, fail_msg)


command_should_trigger_fail_msg_template = \
    '\nMessage with content: \'{}\' at index: {} of given \'should_trigger\' list did not trigger ' \
    'command\'s handler.\nExpected behavior: message_handler should be called for this message'

command_should_not_trigger_fail_msg_template = \
    '\nMessage with content: \'{}\' at index: {} of given \'should_not_trigger\' list did trigger ' \
    'command\'s handler.\nExpected behavior: message_handler should not be called for this message'


# Bobs message should contain all given elements in the list
async def assert_reply_to_contain(test: TestCase, message_text: string, expected_list: List[str]):
    chat, user = init_chat_user()
    await user.send_message(message_text)
    assert_message_contains(test, chat.last_bot_txt(), expected_list)


def assert_message_contains(test: TestCase, reply_text: str, expected_list: List[str]):
    test.assertIsNotNone(reply_text)
    for expected in expected_list:
        test.assertRegex(reply_text, expected)


# Bobs message should contain all given elements in the list
async def assert_reply_to_not_contain(test: TestCase, message_text: str, expected_list: List[type(str)]):
    chat, user = init_chat_user()
    await user.send_message(message_text)
    reply = chat.last_bot_txt()
    test.assertIsNotNone(reply)
    for expected in expected_list:
        test.assertNotRegex(reply, expected)


# Reply should be strictly equal to expected text
async def assert_reply_equal(test: TestCase | django.test.TransactionTestCase, message_text: str, expected: str):
    chat, user = init_chat_user()
    await user.send_message(message_text)
    test.assertEqual(expected, chat.last_bot_txt())


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
    def __init__(self, status_code=0, content='', text=None):
        self.status_code = status_code
        self.content = content
        self.text = text

    def json(self):
        return self.content

    def text(self):
        return self.text


# Can be used as a mock for example with '@mock.patch('requests.post', mock_request_200)'
async def async_mock_response_200(*args, **kwargs) -> MockResponse:
    del args, kwargs
    return MockResponse(status_code=200, content='test')


def mock_response_200(*args, **kwargs) -> MockResponse:
    del args, kwargs
    return MockResponse(status_code=200, content='test')


def mock_async_get_json(content=None):
    """ Mock method for 'get_json' function. Returns a async callback function that is called
        instead. It returns given content as is """

    async def callback(*args, **kwargs):
        return content or {}

    return callback


def async_raises_exception(exception: Exception):
    """ Returns mock function that is async and raises exception given as parameter """

    async def mock_implementation(*args, **kwargs):
        raise exception

    return mock_implementation


def raises_exception(exception: Exception):
    """ Returns mock function that raises exception given as parameter """

    def mock_implementation(*args):
        raise exception

    return mock_implementation


def async_raise_client_response_error(status=0, message=''):
    """ Mock method for 'get_json' function. Returns a async callback function that is called
        instead. It raises ClientResponseError with given status code and message """

    async def callback(*args, **kwargs):
        raise_client_response_error(status=status, message=message)

    return callback


def raise_client_response_error(*args, status=0, message='', **kwargs):
    request_info = RequestInfo(url=URL(), headers=None, method='')
    raise ClientResponseError(status=status, message=message, history=(), request_info=request_info)


def get_json(obj):
    return json.loads(json.dumps(obj, default=lambda o: getattr(o, '__dict__', str(o))))

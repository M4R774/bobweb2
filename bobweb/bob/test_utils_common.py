from unittest import mock

import django
import pytest
from django.test import TestCase
from telegram import Update
from telegram.ext import CallbackContext

from bobweb.bob.tests_mocks_v2 import init_chat_user
from bobweb.bob import main
from bobweb.bob.utils_common import get_caller_from_stack, object_search, reply_long_text_with_markdown, \
    handle_exception_async


@pytest.mark.asyncio
class TestHandleExceptionAsyncDecorator(TestCase):
    # Test 'utils_common.handle_exception_async' decorator
    # Create a mock function with the decorator that is being tested
    @handle_exception_async(exception_type=ValueError, return_value=-1, log_msg='Value error was mitigated')
    async def mock_function_with_decorator(self):
        raise ValueError('No value')

    async def mock_function_without_decorator(self):
        raise ValueError('No value')

    async def test_decorated_function_does_not_raise_an_exception(self):
        # Call the mock method with decorator. If an exception was raised, this would fail
        with self.assertLogs(level='ERROR') as log:
            return_value = await self.mock_function_with_decorator()

            # Expected return value is returned and a error message has been logged
            self.assertEqual(-1, return_value)
            self.assertIn('Value error was mitigated', log.output[0])

        # Now if we call same function without the decorator an exception is raised
        with self.assertRaises(ValueError) as error_context:
            await self.mock_function_without_decorator()
        self.assertEqual('No value', error_context.exception.args[0])


def func_wants_to_know_who_called():
    # Wants to know who called this function and returns that function name
    return get_caller_from_stack().function


def foo():
    return bar()  # only calls bar


def bar():
    # Calls 'get_caller_from_stack' with depth of 2, so function 2 calls from this
    return get_caller_from_stack(stack_depth=2).function


class TestGetPrevCallerFromStack(TestCase):

    def test_direct_caller_with_stack_depth_0(self):
        expected = 'test_direct_caller_with_stack_depth_0'
        result = get_caller_from_stack(0).function
        self.assertEqual(expected, result)

    def test_direct_caller_with_stack_depth_1(self):
        expected = '_callTestMethod'
        result = get_caller_from_stack(1).function
        self.assertEqual(expected, result)

    def test_indirect_caller(self):
        # This is a first "real case". This function tests that the called function
        # 'func_wants_to_know_who_called' can name this test function as this is the
        # previous caller from the context of 'func_wants_to_know_who_called'
        expected = 'test_indirect_caller'
        result = func_wants_to_know_who_called()
        self.assertEqual(expected, result)

    def test_longer_call_stack(self):
        expected = 'test_longer_call_stack'
        result = foo()  # 'foo' calls 'bar' that returns calling function from the depth of 3
        self.assertEqual(expected, result)


# Mock data for object_search tests
data = {
    'foo': {
        'bar': [
            {'baz': 42},
            {'qux': 'hello'},
            {'fig': []}
        ],
        'tuple': ('A', 'B', 'C')
    }
}


# Class structure for tests
class Foo:
    bar: list = [
            {'baz': 42},
            {'qux': 'hello'},
            {'fig': []}
        ]
    tuple: tuple = ('A', 'B', 'C')


class Data:
    foo = Foo()


class TestDictSearch(TestCase):

    def test_object_search_valid_path_and_syntax_with_dictionaries(self):
        # when path is valid, should find value
        self.assertEqual(object_search(data, 'foo', 'bar', 0, 'baz'), 42)
        self.assertEqual(object_search(data, 'foo', 'bar', 1, 'qux'), 'hello')

        # tuples and list can be traversed with index
        self.assertEqual(object_search(data, 'foo', 'tuple', 1), 'B')
        self.assertEqual(object_search(data, 'foo', 'bar', 1), {'qux': 'hello'})

        # when negative index is given, then counts from the end of array
        self.assertEqual(object_search(data, 'foo', 'bar', -1, 'fig'), [])

        # when no arguments are given, should return given dict
        self.assertEqual(object_search(data), data)

    def test_object_search_valid_path_and_syntax_with_objects(self):
        # when path is valid, should find value
        self.assertEqual(object_search(Data(), 'foo', 'bar', 0, 'baz'), 42)
        self.assertEqual(object_search(Data(), 'foo', 'bar', 1, 'qux'), 'hello')

        # tuples and list can be traversed with index
        self.assertEqual(object_search(Data(), 'foo', 'tuple', 1), 'B')
        self.assertEqual(object_search(Data(), 'foo', 'bar', 1), {'qux': 'hello'})

        # when negative index is given, then counts from the end of array
        self.assertEqual(object_search(Data(), 'foo', 'bar', -1, 'fig'), [])

        # when no arguments are given, should return given dict
        test_object = Data()
        self.assertEqual(object_search(test_object), test_object)

    #
    # Tests for situations where object not Found from the given path or there was
    # an error while traversing the dictionary tree. In these cases an errorm-message
    # is logged with DEBUG-level and None is returned
    #

    def test_object_search_with_dict_nothing_found_returns_None_and_debug_logs_error(self):
        with self.assertLogs(level='DEBUG') as log:
            # when given path is invalid or item does not exist, then returns None
            self.assertIsNone(object_search(data, 'invalid_path'))
            last_log = log.output[-1]
            # when error is raised from the root node, then log msg contains information that no traversal was done
            self.assertIn('Error searching value from object: \'invalid_path\'', last_log)
            self.assertIn('Error raised from dict root, no traversal done', last_log)
            # In addition, log contains details of the call that caused the error
            # Note: Module depth is affected by working directory. If locally working directory is set to be
            # root of the project, the module string contains whole path. If ran from the test module without another
            # working directory set, will only contain current module
            self.assertRegex(last_log, r'\[module\]: (bobweb\.bob\.)?test_utils_common')
            self.assertIn('[function]: test_object_search_with_dict_nothing_found_returns_None_and_debug_logs_error', last_log)
            # Using regex not to tie row number to the test's expected string
            self.assertRegex(last_log, r"\[row\]: \d*, \[\*args content\]: \('invalid_path',\)")

            # when out of range index is given, then returns none and logs error
            self.assertIsNone(object_search(data, 'foo', 'bar', 5, 'baz'))
            last_log = log.output[-1]
            # when error is raised after traversal, then log msg contains traversed path
            # contains all same information as in the above example. Just to demonstrate:
            self.assertIn('list index out of range. Path traversed before error: [\'foo\'][\'bar\']', last_log)
            self.assertRegex(last_log, r"\[row\]: \d*, \[\*args content\]: \('foo', 'bar', 5, 'baz'\)")

    def test_object_search_with_object_nothing_found_returns_None_and_debug_logs_error(self):
        with self.assertLogs(level='DEBUG') as log:
            # when given path is invalid or item does not exist, then returns None
            self.assertIsNone(object_search(Data(), 'invalid_path'))
            last_log = log.output[-1]
            # when error is raised from the root node, then log msg contains information that no traversal was done
            self.assertIn('Error searching value from object: \'Data\' object has no attribute \'invalid_path\'',
                          last_log)

    def test_return_None_gived_debug_log_if_missmatch_between_current_node_and_arg_type(self):
        with self.assertLogs(level='DEBUG') as log:
            # If index is given while traversing dict, then returns None and logs error
            self.assertIsNone(object_search(data, 0))
            self.assertIn('Expected list or tuple but got dict', log.output[-1])

            # If attribute name is given while traversing a list, then returns None and logs error
            self.assertIsNone(object_search(data, 'foo', 'bar', 'first_item'))
            self.assertIn('Expected object or dict but got list', log.output[-1])

            # If given path is None, given dict is returned as is
            self.assertIsNone(object_search(data, None))
            self.assertIn('Expected arguments to be of any type [str|int] but got NoneType', log.output[-1])

            # If argument path is of unsupported type, None is returned
            self.assertIsNone(object_search(data, []))
            self.assertIn('Expected arguments to be of any type [str|int] but got list', log.output[-1])

            self.assertIsNone(object_search(data, {'foo': 'bar'}))
            self.assertIn('Expected arguments to be of any type [str|int] but got dict', log.output[-1])

            # Valid path and default value is given => value from path is returned
            self.assertEqual(object_search(data, 'foo', 'bar', 0, 'baz', default=101), 42)
            # Invalid path and default value is given => default is returned
            self.assertEqual(object_search(data, 'invalid_path', default=101), 101)


async def message_handler_echo_mock(update: Update, context: CallbackContext = None):
    # Maximum length is total maximum allowed length for message. As each message will
    # contain a footer indicating its number and total number of messages, content of
    # messages will be shorter than the given msg_max_length (by 10 characters)
    await reply_long_text_with_markdown(update, update.effective_message.text,
                                        do_quote=False, min_msg_length=10, max_msg_length=35)


@mock.patch('bobweb.bob.message_handler.handle_update', message_handler_echo_mock)
@pytest.mark.asyncio
class TestReplyLongText(django.test.TransactionTestCase):
    """ Tests that reply_long_text works as expected and long messages are
        sent as multiple messages. All Telegram API replies are mocked to be
        using reply_long_text to make testing easier.
        For this classes test cases normal message_handler is mock patched with
        a version that just echoes users input sent with reply_long_text."""

    async def test_short_message_is_sent_as_is(self):
        chat, user = init_chat_user()
        await user.send_message('test')
        self.assertEqual('test', chat.last_bot_txt())
        self.assertEqual(1, len(chat.bot.messages))

    async def test_long_message_is_sent_in_multiple_messages(self):
        chat, user = init_chat_user()
        # If message with 40 asterisks is sent, it is split at predefined maximum length of 35 - 10 = 25 characters.
        # Second message will contain the rest.
        await user.send_message('*' * 40)
        self.assertEqual('*' * 25 + '\n(1/2)', chat.bot.messages[-2].text)
        self.assertEqual('*' * 15 + '\n(2/2)', chat.bot.messages[-1].text)
        self.assertEqual(2, len(chat.bot.messages))

        # Check that the last message sent by bot is replying to the first message
        self.assertEqual(chat.bot.messages[-1].reply_to_message.id, chat.bot.messages[-2].id)



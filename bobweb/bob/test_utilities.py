from django.test import TestCase

from bobweb.bob.utils_common import get_caller_from_stack, dict_search


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


# Mock data for dict_search tests
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


class TestDictSearch(TestCase):

    def test_dict_search_valid_path_and_syntax(self):
        # when path is valid, should find value
        self.assertEqual(dict_search(data, 'foo', 'bar', 0, 'baz'), 42)
        self.assertEqual(dict_search(data, 'foo', 'bar', 1, 'qux'), 'hello')

        # tuples and list can be traversed with index
        self.assertEqual(dict_search(data, 'foo', 'tuple', 1), 'B')
        self.assertEqual(dict_search(data, 'foo', 'bar', 1), {'qux': 'hello'})

        # when negative index is given, then counts from the end of array
        self.assertEqual(dict_search(data, 'foo', 'bar', -1, 'fig'), [])

        # when no arguments are given, should return given dict
        self.assertEqual(dict_search(data), data)

    #
    # Tests for situations where object not Found from the given path or there was
    # an error while traversing the dictionary tree. In these cases an errorm-message
    # is logged with DEBUG-level and None is returned
    #

    def test_dict_search_nothing_found_returns_None_and_debug_logs_error(self):
        with self.assertLogs(level='DEBUG') as log:

            # when given path is invalid or item does not exist, then returns None
            self.assertIsNone(dict_search(data, 'invalid_path'))
            last_log = log.output[-1]
            # when error is raised from the root node, then log msg contains information that no traversal was done
            self.assertIn('Error searching value from dictionary: \'invalid_path\'', last_log)
            self.assertIn('Error raised from dict root, no traversal done', last_log)
            # In addition, log contains details of the call that caused the error
            # Note: Module depth is affected by working directory. If locally working directory is set to be
            # root of the project, the module string contains whole path. If ran from the test module without another
            # working directory set, will only contain current module
            self.assertRegex(last_log, r'\[module\]: (bobweb\.bob\.)?test_utilities')
            self.assertIn('[function]: test_dict_search_nothing_found_returns_None_and_debug_logs_error', last_log)
            # Using regex not to tie row number to the test's expected string
            self.assertRegex(last_log, r"\[row\]: \d*, \[\*args content\]: \('invalid_path',\)")

            # when out of range index is given, then returns none and logs error
            self.assertIsNone(dict_search(data, 'foo', 'bar', 5, 'baz'))
            last_log = log.output[-1]
            # when error is raised after traversal, then log msg contains traversed path
            # contains all same information as in the above example. Just to demonstrate:
            self.assertIn('list index out of range. Path traversed before error: [\'foo\'][\'bar\']', last_log)
            self.assertRegex(last_log, r"\[row\]: \d*, \[\*args content\]: \('foo', 'bar', 5, 'baz'\)")


    def test_return_None_gived_debug_log_if_missmatch_between_current_node_and_arg_type(self):
        with self.assertLogs(level='DEBUG') as log:
            # If index is given while traversing dict, then returns None and logs error
            self.assertIsNone(dict_search(data, 0))
            self.assertIn('Expected list or tuple but got dict', log.output[-1])

            # If attribute name is given while traversing a list, then returns None and logs error
            self.assertIsNone(dict_search(data, 'foo', 'bar', 'first_item'))
            self.assertIn('Expected dict but got list', log.output[-1])

            # If given path is None, given dict is returned as is
            self.assertIsNone(dict_search(data, None))
            self.assertIn('Expected arguments to be of any type [str|int] but got NoneType', log.output[-1])

            # If argument path is of unsupported type, None is returned
            self.assertIsNone(dict_search(data, []))
            self.assertIn('Expected arguments to be of any type [str|int] but got list', log.output[-1])

            self.assertIsNone(dict_search(data, {'foo': 'bar'}))
            self.assertIn('Expected arguments to be of any type [str|int] but got dict', log.output[-1])

            # Valid path and default value is given => value from path is returned
            self.assertEqual(dict_search(data, 'foo', 'bar', 0, 'baz', default=101), 42)
            # Invalid path and default value is given => default is returned
            self.assertEqual(dict_search(data, 'invalid_path', default=101), 101)


    def test_dict_search_raises_error_if_dict_parameter_is_invalid(self):
        # If first argument is not dict an error is raised and type of the first argument is given
        with self.assertRaises(TypeError) as context_manager:
            dict_search(None)
            self.assertEqual(context_manager.exception.__str__(), 'Expected first argument to be dict but got NoneType')

            dict_search('foo', 'bar')
            self.assertEqual(context_manager.exception.__str__(), 'Expected first argument to be dict but got str')

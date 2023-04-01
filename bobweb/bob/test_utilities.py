from django.test import TestCase

from bobweb.bob.utils_common import get_caller_from_stack, dict_search


def func_wants_to_know_who_called():
    # Wants to know who called this function and returns that function name
    return get_caller_from_stack().function


def foo():
    return bar()  # only calls bar


def bar():
    return get_caller_from_stack(stack_depth=3).function


class TestGetPrevCallerFromStack(TestCase):

    def test_direct_caller_with_stack_depth_0(self):
        expected = 'get_caller_from_stack'
        result = get_caller_from_stack(0).function
        self.assertEqual(expected, result)

    def test_direct_caller_with_stack_depth_1(self):
        expected = 'test_direct_caller'
        result = get_caller_from_stack(1).function
        self.assertEqual(expected, result)

    def test_direct_caller_with_stack_depth_2(self):
        expected = '_callTestMethod'
        result = get_caller_from_stack(2).function
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


    def test_dict_search_nothing_found(self):
        # Test with logging context
        with self.assertLogs(level='DEBUG') as log:

            # when given path is invalid or item does not exist, then returns None
            self.assertIsNone(dict_search(data, 'invalid_path'))
            # when error is raised from the root node, then log msg contains information that no traversal was done
            self.assertIn('\'invalid_path\'. Error raised from dict root, no traversal done', log.output[-1])

            # when out of range index is given, then returns none and logs error
            self.assertIsNone(dict_search(data, 'foo', 'bar', 5, 'baz'))
            # when error is raised after traversal, then log msg contains traversed path
            self.assertIn('list index out of range. Path traversed before error: [\'foo\'][\'bar\']', log.output[-1])

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

        # If first argument is not dict an error is raised and type of the first argument is given
        with self.assertRaises(TypeError) as context_manager:
            dict_search(None)
            self.assertEqual(context_manager.exception.__str__(), 'Expected first argument to be dict but got NoneType')

            dict_search('foo', 'bar')
            self.assertEqual(context_manager.exception.__str__(), 'Expected first argument to be dict but got str')

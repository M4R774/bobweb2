from django.test import TestCase

from bobweb.bob.utils_common import get_caller_from_stack


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


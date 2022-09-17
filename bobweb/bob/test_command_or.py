import os
from unittest import TestCase, mock

import main
from command_or import OrCommand
from utils_test import assert_has_reply_to, assert_no_reply_to, assert_reply_contains, always_last_choice, \
    assert_reply_equal


@mock.patch('random.choice', lambda values: values[0])
class Test(TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        os.system("python ../web/manage.py migrate")

    def test_no_parameter_before_or_after_should_not_reply(self):
        assert_no_reply_to(self, '/vai')

    def test_no_prefix_no_reply(self):
        assert_no_reply_to(self, 'vai')

    def test_only_one_parameter_should_not_reply(self):
        assert_no_reply_to(self, 'test /vai')
        assert_no_reply_to(self, '/vai test')

    def test_parameter_before_and_after_should_reply(self):
        assert_has_reply_to(self, 'test .vai test')

    def test_get_given_parameter(self):
        message = 'a !vai b .vai c /vai d'
        parameter_expected = ['a', 'b', 'c', 'd']
        parameter_actual = OrCommand().get_parameters(message)
        self.assertEqual(parameter_expected, parameter_actual)

    def test_should_strip_white_spaces(self):
        assert_reply_equal(self, '\n  a \t .vai \n \r b\n\t\r?', 'a')

    def test_question_mark_is_removed_from_last_paramter(self):
        with mock.patch('random.choice', lambda values: values[-1]):
            assert_reply_equal(self, 'a .vai b?', 'b')

    def test_return_random_from_any_number_of_parameters(self):
        assert_reply_contains(self, "rahat .vai kolmipyörä?", ['rahat'])
        assert_reply_contains(self, "a .vai b .vai  c?", ['a'])

        with mock.patch('random.choice', lambda values: values[-1]):
            assert_reply_contains(self, "a .vai b .vai  c?", ['c'])

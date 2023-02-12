import os

import django
from django.test import TestCase
from unittest import mock

from bobweb.bob import main
from bobweb.bob.command_or import OrCommand
from bobweb.bob.tests_utils import assert_reply_to_contain, \
    assert_reply_equal, assert_command_triggers


@mock.patch('random.choice', lambda values: values[0])
class Test(TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super(Test, cls).setUpClass()
        django.setup()
        os.system("python bobweb/web/manage.py migrate")

    def test_command_triggers(self):
        # Should have some text before and after the command
        should_trigger = ['test /vai test', 'test !vai test', 'test .vai test']
        should_not_trigger = ['vai', '/vai', 'test /vai', '/vai test']
        assert_command_triggers(self, OrCommand, should_trigger, should_not_trigger)

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
        assert_reply_to_contain(self, "rahat .vai kolmipyörä?", ['rahat'])
        assert_reply_to_contain(self, "a .vai b .vai  c?", ['a'])

        with mock.patch('random.choice', lambda values: values[-1]):
            assert_reply_to_contain(self, "a .vai b .vai  c?", ['c'])

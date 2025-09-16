import os

import django
import pytest
from django.core import management
from django.test import TestCase
from unittest import mock

from bot import main
from bot.commands.or_command import OrCommand
from bot.tests_utils import assert_reply_to_contain, \
    assert_reply_equal, assert_command_triggers


@pytest.mark.asyncio
@mock.patch('random.choice', lambda values: values[0])
class OrCommandTest(django.test.TransactionTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super(OrCommandTest, cls).setUpClass()
        django.setup()
        management.call_command('migrate')

    async def test_command_triggers(self):
        # Should have some text before and after the command
        should_trigger = ['test /vai test', 'test !vai test', 'test .vai test']
        should_not_trigger = ['vai', '/vai', 'test /vai', '/vai test']
        await assert_command_triggers(self, OrCommand, should_trigger, should_not_trigger)

    async def test_get_given_parameter(self):
        message = 'a !vai b .vai c /vai d'
        parameter_expected = ['a', 'b', 'c', 'd']
        parameter_actual = OrCommand().get_parameters(message)
        self.assertEqual(parameter_expected, parameter_actual)

    async def test_should_strip_white_spaces(self):
        await assert_reply_equal(self, '\n  a \t .vai \n \r b\n\t\r?', 'a')

    async def test_question_mark_is_removed_from_last_paramter(self):
        with mock.patch('random.choice', lambda values: values[-1]):
            await assert_reply_equal(self, 'a .vai b?', 'b')

    async def test_return_random_from_any_number_of_parameters(self):
        await assert_reply_to_contain(self, "rahat .vai kolmipyörä?", ['rahat'])
        await assert_reply_to_contain(self, "a .vai b .vai  c?", ['a'])

        with mock.patch('random.choice', lambda values: values[-1]):
            await assert_reply_to_contain(self, "a .vai b .vai  c?", ['c'])

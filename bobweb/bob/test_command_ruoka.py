import os

import django
import pytest
from django.core import management
from django.test import TestCase
from unittest import mock

from bobweb.bob import main
from bobweb.bob.command_ruoka import RuokaCommand
from bobweb.bob.tests_utils import assert_reply_to_contain, \
    assert_get_parameters_returns_expected_value, assert_command_triggers


@pytest.mark.asyncio
@mock.patch('random.choice', lambda values: values[0])
class RuokaCommandTest(django.test.TransactionTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super(RuokaCommandTest, cls).setUpClass()
        django.setup()
        management.call_command('migrate')

    async def test_command_triggers(self):
        should_trigger = ['/ruoka', '!ruoka', '.ruoka', '/RUOKA', '/ruoka test']
        should_not_trigger = ['ruoka', 'test /ruoka', ]
        await assert_command_triggers(self, RuokaCommand, should_trigger, should_not_trigger)

    async def test_get_given_parameter(self):
        assert_get_parameters_returns_expected_value(self, '!ruoka', RuokaCommand())

    async def test_should_return_a_link(self):
        await assert_reply_to_contain(self, '.ruoka', ['tahnat-ja-marinadit-lisukkeet-gluteeniton'])

    async def test_should_return_item_with_given_prompt_in_link(self):
        await assert_reply_to_contain(self, '!ruoka mozzarella', ['mozzarella-gnocchivuoka'])

    async def test_should_return_random_item_if_no_recipe_link_contains_prompt(self):
        with mock.patch('random.choice', lambda values: values[2]):
            await assert_reply_to_contain(self, '/ruoka asdasdasdasdasd', ['kookos-linssikeitto'])

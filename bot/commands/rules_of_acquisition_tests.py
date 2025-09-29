import os

import django
import pytest
from django.core import management
from django.test import TestCase
from unittest import mock

from bot import main
from bot.commands.rules_of_acquisition import RulesOfAquisitionCommand
from bot.tests_utils import assert_reply_to_contain, \
    assert_command_triggers

EXPECTED_ANSWER = 'Kun olet saanut heidän rahansa'


@pytest.mark.asyncio
class RulesOfAcquisitionTest(django.test.TransactionTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super(RulesOfAcquisitionTest, cls).setUpClass()
        django.setup()
        management.call_command('migrate')

    async def test_command_triggers(self):
        should_trigger = ['/sääntö', '!sääntö', '.sääntö', '/SÄÄNTÖ', '/sääntö test', '/saanto']
        should_not_trigger = ['sääntö', 'test /sääntö']
        await assert_command_triggers(self, RulesOfAquisitionCommand, should_trigger, should_not_trigger)

    @mock.patch('random.choice', lambda values: values[0])
    async def test_without_number_should_return_random_rule(self):
        await assert_reply_to_contain(self, '/sääntö', [EXPECTED_ANSWER])
        await assert_reply_to_contain(self, '/sääntö -1', [EXPECTED_ANSWER])
        await assert_reply_to_contain(self, '/sääntö asd', [EXPECTED_ANSWER])

    async def test_should_contain_predefined_rule(self):
        await assert_reply_to_contain(self, '/sääntö 1', [EXPECTED_ANSWER])
        await assert_reply_to_contain(self, '.sääntö 299', ['Kun käytät jotakuta hyväksesi, kannattaa muistaa kiittää'])



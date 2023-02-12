import os

import django
from django.test import TestCase
from unittest import mock

from bobweb.bob import main
from bobweb.bob.command_rules_of_acquisition import RulesOfAquisitionCommand
from bobweb.bob.tests_utils import assert_reply_to_contain, \
    assert_command_triggers


class Test(TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super(Test, cls).setUpClass()
        django.setup()
        os.system("python bobweb/web/manage.py migrate")

    def test_command_triggers(self):
        should_trigger = ['/sääntö', '!sääntö', '.sääntö', '/SÄÄNTÖ', '/sääntö test']
        should_not_trigger = ['sääntö', 'test /sääntö']
        assert_command_triggers(self, RulesOfAquisitionCommand, should_trigger, should_not_trigger)

    @mock.patch('random.choice', lambda values: values[0])
    def test_without_number_should_return_random_rule(self):
        assert_reply_to_contain(self, '/sääntö', ['Kun olet saanut heidän rahansa'])
        assert_reply_to_contain(self, '/sääntö -1', ['Kun olet saanut heidän rahansa'])
        assert_reply_to_contain(self, '/sääntö asd', ['Kun olet saanut heidän rahansa'])

    def test_should_contain_predefined_rule(self):
        assert_reply_to_contain(self, '/sääntö 1', ['Kun olet saanut heidän rahansa'])
        assert_reply_to_contain(self, '.sääntö 299', ['Kun käytät jotakuta hyväksesi, kannattaa muistaa kiittää'])



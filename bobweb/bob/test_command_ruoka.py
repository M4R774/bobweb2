import os
from django.test import TestCase
from unittest import mock

from bobweb.bob import main
from bobweb.bob.command_ruoka import RuokaCommand
from bobweb.bob.tests_utils import assert_has_reply_to, assert_no_reply_to, assert_reply_to_contain, \
    assert_get_parameters_returns_expected_value


@mock.patch('random.choice', lambda values: values[0])
class Test(TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        os.system("python bobweb/web/manage.py migrate")

    def test_command_should_reply(self):
        assert_has_reply_to(self, '/ruoka')

    def test_no_prefix_no_reply(self):
        assert_no_reply_to(self, 'ruoka')

    def test_text_before_command_no_reply(self):
        assert_no_reply_to(self, 'test /ruoka')

    def test_text_after_command_should_reply(self):
        assert_has_reply_to(self, '/ruoka test')

    def test_get_given_parameter(self):
        assert_get_parameters_returns_expected_value(self, '!ruoka', RuokaCommand())

    def test_should_return_a_link(self):
        assert_reply_to_contain(self, '.ruoka', ['tahnat-ja-marinadit-lisukkeet-gluteeniton'])

    def test_should_return_item_with_given_prompt_in_link(self):
        assert_reply_to_contain(self, '!ruoka mozzarella', ['mozzarella-gnocchivuoka'])

    def test_should_return_random_item_if_no_recipe_link_contains_prompt(self):
        with mock.patch('random.choice', lambda values: values[2]):
            assert_reply_to_contain(self, '/ruoka asdasdasdasdasd', ['kookos-linssikeitto'])

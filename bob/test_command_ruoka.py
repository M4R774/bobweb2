import os
from unittest import TestCase, mock

import main
from command_ruoka import RuokaCommand
from utils_test import assert_has_reply_to, assert_no_reply_to, assert_reply_contains


@mock.patch('random.choice', lambda values: values[0])
class Test(TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        os.system("python ../web/manage.py migrate")

    def test_command_should_reply(self):
        assert_has_reply_to(self, '/ruoka')

    def test_no_prefix_no_reply(self):
        assert_no_reply_to(self, 'ruoka')

    def test_text_before_command_no_reply(self):
        assert_no_reply_to(self, 'test /ruoka')

    def test_text_after_command_should_reply(self):
        assert_has_reply_to(self, '/ruoka test')

    def test_get_given_parameter(self):
        message = '!ruoka test . test/test-test\ntest\ttest .vai test \n '
        parameter_expected = 'test . test/test-test\ntest\ttest .vai test'
        parameter_actual = RuokaCommand().get_parameters(message)
        self.assertEqual(parameter_expected, parameter_actual)

    def test_should_return_a_link(self):
        assert_reply_contains(self, '.ruoka', ['tahnat-ja-marinadit-lisukkeet-gluteeniton'])

    def test_should_return_item_with_given_prompt_in_link(self):
        assert_reply_contains(self, '!ruoka mozzarella', ['mozzarella-gnocchivuoka'])

    def test_should_return_random_item_if_no_recipe_link_contains_prompt(self):
        with mock.patch('random.choice', lambda values: values[2]):
            assert_reply_contains(self, '/ruoka asdasdasdasdasd', ['kookos-linssikeitto'])

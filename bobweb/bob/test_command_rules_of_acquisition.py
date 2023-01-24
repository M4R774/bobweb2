import os
from django.test import TestCase
from unittest import mock

from bobweb.bob import main
from bobweb.bob.tests_utils import assert_has_reply_to, assert_no_reply_to, assert_reply_to_contain


class Test(TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        os.system("python bobweb/web/manage.py migrate")

    def test_command_should_reply(self):
        assert_has_reply_to(self, '/sääntö')

    def test_no_prefix_no_reply(self):
        assert_no_reply_to(self, 'sääntö')

    def test_text_before_command_no_reply(self):
        assert_no_reply_to(self, 'test /sääntö')

    def test_text_after_command_should_reply(self):
        assert_has_reply_to(self, '/sääntö test')

    @mock.patch('random.choice', lambda values: values[0])
    def test_without_number_should_return_random_rule(self):
        assert_reply_to_contain(self, '/sääntö', ['Kun olet saanut heidän rahansa'])
        assert_reply_to_contain(self, '/sääntö -1', ['Kun olet saanut heidän rahansa'])
        assert_reply_to_contain(self, '/sääntö asd', ['Kun olet saanut heidän rahansa'])

    def test_should_contain_predefined_rule(self):
        assert_reply_to_contain(self, '/sääntö 1', ['Kun olet saanut heidän rahansa'])
        assert_reply_to_contain(self, '.sääntö 299', ['Kun käytät jotakuta hyväksesi, kannattaa muistaa kiittää'])



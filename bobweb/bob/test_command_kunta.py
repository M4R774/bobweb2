import os

from unittest import IsolatedAsyncioTestCase

from bobweb.bob.tests_utils import assert_has_reply_to, assert_no_reply_to

import django

os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    "bobweb.web.web.settings"
)

os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"
django.setup()


class Test(IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        os.system("python bobweb/web/manage.py migrate")

    def test_command_should_reply(self):
        assert_has_reply_to(self, '/kunta')

    def test_no_prefix_no_reply(self):
        assert_no_reply_to(self, 'kunta')

    def test_text_before_command_no_reply(self):
        assert_no_reply_to(self, 'test /kunta')

    def test_text_after_command_should_reply(self):
        assert_has_reply_to(self, '/kunta test')

    def test_no_prompt_should_reply(self):
       assert_has_reply_to(self, '/kunta')

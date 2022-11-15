import os
import sys
from unittest import TestCase, mock

from bobweb.bob import main
from bobweb.bob.command_kuulutus import KuulutusCommand
from bobweb.bob.utils_test import assert_has_reply_to, assert_no_reply_to, assert_reply_to_contains, \
    assert_get_parameters_returns_expected_value

import django
os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    "bobweb.web.web.settings"
)
os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"
django.setup()
from bobweb.web.bobapp.models import Chat, TelegramUser, ChatMember, Bob, GitUser


class Test(TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        os.system("python bobweb/web/manage.py migrate")

    def test_command_should_reply_and_is_case_insensitive(self):
        assert_has_reply_to(self, '/kuulutus')
        assert_has_reply_to(self, '.Kuulutus')
        assert_has_reply_to(self, '!kuulUTUS')

    def test_no_prefix_no_reply(self):
        assert_no_reply_to(self, 'kuulutus')

    def test_text_before_command_no_reply(self):
        assert_no_reply_to(self, 'test /kuulutus')

    def test_text_after_command_should_reply(self):
        assert_has_reply_to(self, '/kuulutus test')

    def test_get_given_parameter(self):
        assert_get_parameters_returns_expected_value(self, '!kuulutus', KuulutusCommand())

    def test_parameters_are_case_insensitive(self):
        with mock.patch('bobweb.bob.database.get_chat', lambda *args, **kwargs: mock.Mock(spec=Chat)):
            assert_reply_to_contains(self, '/kuulutus off', ['Kuulutukset ovat nyt pois päältä.'])
            assert_reply_to_contains(self, '/kuulutus OFf', ['Kuulutukset ovat nyt pois päältä.'])
            assert_reply_to_contains(self, '.kuulutus on', ['Kuulutukset ovat nyt päällä.'])
            assert_reply_to_contains(self, '.kuulutus oN', ['Kuulutukset ovat nyt päällä.'])

    def test_no_parameter_new_chat_should_give_help_with_broadcast_on(self):
        chat = mock.Mock(spec=Chat)
        chat.broadcast_enabled = True

        with mock.patch('bobweb.bob.database.get_chat', lambda *args, **kwargs: chat):
            assert_reply_to_contains(self, '/kuulutus', ['Käyttö', 'Kytkee kuulutukset', 'ovat päällä'])

    def test_no_parameter_broadcast_is_off_should_give_help_with_broadcast_off(self):
        chat = mock.Mock(spec=Chat)
        chat.broadcast_enabled = False

        with mock.patch('bobweb.bob.database.get_chat', lambda *args, **kwargs: chat):
            assert_reply_to_contains(self, '/kuulutus', ['Käyttö', 'Kytkee kuulutukset', 'ovat pois päältä'])

    def test_reply_and_value_change_with_parameter_on(self):
        chat = mock.Mock(spec=Chat)
        chat.broadcast_enabled = False

        with mock.patch('bobweb.bob.database.get_chat', lambda *args, **kwargs: chat):
            assert_reply_to_contains(self, '.kuulutus on', ['Kuulutukset ovat nyt päällä.'])
            self.assertTrue(chat.broadcast_enabled)

    def test_reply_and_value_change_with_parameter_off(self):
        chat = mock.Mock(spec=Chat)
        chat.broadcast_enabled = True

        with mock.patch('bobweb.bob.database.get_chat', lambda *args, **kwargs: chat):
            assert_reply_to_contains(self, '.kuulutus off', ['Kuulutukset ovat nyt pois päältä.'])
            self.assertFalse(chat.broadcast_enabled)

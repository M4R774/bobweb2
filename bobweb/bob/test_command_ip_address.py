from unittest import mock
from unittest.mock import patch

import django
import pytest
import requests
from django.core import management
from django.test import TestCase
from requests import RequestException

import bobweb.bob.command_ip_address
from bobweb.bob import database
from bobweb.bob.command_ip_address import IpAddressCommand
from bobweb.bob.tests_mocks_v2 import init_chat_user
from bobweb.bob.tests_utils import assert_command_triggers, MockResponse


class IpCommandApiEndpointPingTest(TestCase):
    """ Smoke test against the real api """

    async def test_epic_games_api_endpoint_ok(self):
        res = requests.get('https://api.ipify.org')
        self.assertEqual(200, res.status_code)


@pytest.mark.asyncio
@mock.patch('requests.get', lambda *args, **kwargs: MockResponse(status_code=200, text='1.2.3.4'))
class IpAddressCommandTests(django.test.TransactionTestCase):

    @classmethod
    def setUpClass(cls) -> None:
        super(IpAddressCommandTests, cls).setUpClass()
        management.call_command('migrate')

    async def test_should_be_enabled_only_in_specified_chat(self):
        # Command should only be enabled in predefined chats
        chat, user = init_chat_user()

        # As new chat is created it is not set as the error_log_chat.
        bob = database.get_the_bob()
        self.assertIsNone(bob.error_log_chat)

        # Bot should not respond anything.
        await user.send_message('/ip')
        self.assertEqual(0, len(chat.bot.messages))

        # Now if the chat is set as the error_log_chat, bot should respond
        bob.error_log_chat = database.get_chat(chat.id)
        bob.save()
        await user.send_message('/ip')
        self.assertEqual('IP-osoite on: 1.2.3.4 📟', chat.last_bot_txt())
        self.assertEqual(1, len(chat.bot.messages))


@pytest.mark.asyncio
# By default, if nothing else is defined, all request.get requests are returned with this mock
@mock.patch('requests.get', lambda *args, **kwargs: MockResponse(status_code=200, text='1.2.3.4'))
@patch.object(bobweb.bob.command_ip_address.IpAddressCommand, 'is_enabled_in', lambda self, chat: True)
class IpAddressCommandTestsWithMocks(django.test.TransactionTestCase):
    command_class = IpAddressCommand
    command_str = 'ip'

    @classmethod
    def setUpClass(cls) -> None:
        super(IpAddressCommandTestsWithMocks, cls).setUpClass()
        management.call_command('migrate')

    async def test_command_triggers(self):
        should_trigger = [f'/{self.command_str}', f'!{self.command_str}', f'.{self.command_str}',
                          f'/{self.command_str.upper()}']
        should_not_trigger = [f'{self.command_str}', f'test /{self.command_str}', f'/{self.command_str} test']
        await assert_command_triggers(self, self.command_class, should_trigger, should_not_trigger)

    async def test_should_inform_if_fetch_failed(self):
        with mock.patch('requests.get', lambda *args, **kwargs: MockResponse(status_code=404)):
            chat, user = init_chat_user()
            await user.send_message('/ip')
            expected_reply = 'IP-osoitteen haku epäonnistui.\napi.ipify.org vastasi statuksella: 404'
            self.assertEqual(expected_reply, chat.last_bot_txt())

    async def test_should_inform_if_exception_was_raised(self):
        def raise_exception(*args, **kwargs):
            raise RequestException('test exception')

        with mock.patch('requests.get', raise_exception):
            chat, user = init_chat_user()
            await user.send_message('/ip')
            expected_reply = 'IP-osoitteen haku epäonnistui.\nVirhe: test exception'
            self.assertEqual(expected_reply, chat.last_bot_txt())

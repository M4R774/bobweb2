from unittest import mock
from unittest.mock import Mock

import aiohttp
import django
import pytest
from django.core import management
from django.test import TestCase

import bot
from bot import main, database
from bot.commands.ip_address import IpAddressCommand
from bot.tests_mocks_v2 import init_chat_user
from bot.tests_utils import assert_command_triggers, MockResponse, mock_http_response


@pytest.mark.asyncio
@mock.patch('bot.async_http.get', mock_http_response(response_body='1.2.3.4.5.6'))  # NOSONAR (S1313)
class IpAddressCommandTests(django.test.TransactionTestCase):

    @classmethod
    def setUpClass(cls) -> None:
        super(IpAddressCommandTests, cls).setUpClass()
        management.call_command('migrate')

    async def test_should_be_enabled_only_in_specified_chat(self):
        # Command should only be enabled in predefined chats
        chat, user = init_chat_user()

        # As new chat is created it is not set as the error_log_chat.
        bot = database.get_bot()
        self.assertIsNone(bot.error_log_chat)

        # Bot should not respond anything.
        await user.send_message('/ip')
        self.assertEqual(0, len(chat.bot.messages))

        # Now if the chat is set as the error_log_chat, bot should respond
        bot.error_log_chat = database.get_chat(chat.id)
        bot.save()
        await user.send_message('/ip')
        self.assertEqual('IP-osoite on: 1.2.3.4.5.6 📟', chat.last_bot_txt())
        self.assertEqual(1, len(chat.bot.messages))


@pytest.mark.asyncio
# By default, if nothing else is defined, all request.get requests are returned with this mock
@mock.patch('bot.async_http.get', mock_http_response(response_body='1.2.3.4'))
@mock.patch.object(bot.commands.ip_address.IpAddressCommand, 'is_enabled_in', lambda self, chat: True)
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
        with mock.patch('bot.async_http.get', mock_http_response(status=404)):
            chat, user = init_chat_user()
            await user.send_message('/ip')
            expected_reply = 'IP-osoitteen haku epäonnistui.\napi.ipify.org vastasi statuksella: 404'
            self.assertEqual(expected_reply, chat.last_bot_txt())

    async def test_should_inform_if_exception_was_raised(self):
        def raise_exception(*args, **kwargs):
            raise aiohttp.ClientResponseError(Mock(), (), message='test exception',)

        with mock.patch('bot.async_http.get', raise_exception):
            chat, user = init_chat_user()
            await user.send_message('/ip')
            expected_reply = 'IP-osoitteen haku epäonnistui.\nVirhe: test exception'
            self.assertEqual(expected_reply, chat.last_bot_txt())

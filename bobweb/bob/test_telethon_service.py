import datetime
import os
from unittest.mock import Mock, AsyncMock

import django
import pytest
from django.core import management
from django.test import TestCase
from unittest import mock

from freezegun import freeze_time
from freezegun.api import FrozenDateTimeFactory

import bobweb
from bobweb.bob import telethon_service

os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    "bobweb.web.web.settings"
)
os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"
django.setup()


@pytest.mark.asyncio
class TestTelethonService(TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        super(TestTelethonService, cls).setUpClass()
        management.call_command('migrate')

    def test_logs_warning_if_telethon_required_env_vars_not_defined(self):
        bobweb.bob.config.tg_client_api_id = None
        bobweb.bob.config.tg_client_api_hash = None
        # Test that logger.warning is called
        with self.assertLogs(level='WARNING') as log:
            # Should return false
            result = telethon_service.are_telegram_client_env_variables_set()
            self.assertFalse(result)

            # And should have logged a warning
            expected_to_be_in_warning = 'Telegram client api ID and api Hash environment variables are missing'
            self.assertIn(expected_to_be_in_warning, log.output[-1])

    def test_logs_warning_if_telethon_required_env_vars_are_empty_string(self):
        bobweb.bob.config.tg_client_api_id = ""
        bobweb.bob.config.tg_client_api_hash = ""
        with self.assertLogs(level='WARNING') as log:
            result = telethon_service.are_telegram_client_env_variables_set()
            self.assertFalse(result)

            expected_to_be_in_warning = 'Telegram client api ID and api Hash environment variables are missing'
            self.assertIn(expected_to_be_in_warning, log.output[-1])

    async def test_raises_exception_if_telethon_client_initialization_is_called_and_env_vars_not_defined(self):
        bobweb.bob.config.tg_client_api_id = None
        bobweb.bob.config.tg_client_api_hash = None
        # Test that should raise an exception if client initialization is called
        with self.assertRaises(Exception) as context:
            await telethon_service.client.initialize_and_get_telethon_client()
        self.assertEqual('Telegram client api ID and api Hash environment variables are missing',
                         context.exception.args[0])

    async def test_raises_exception_if_client_is_None_and_trying_to_connect(self):
        with self.assertRaises(Exception) as context:
            client_wrapper = telethon_service.TelethonClientWrapper()
            await client_wrapper._connect()
        self.assertEqual('No Client initialized, cannot connect.', context.exception.args[0])

    @freeze_time(datetime.datetime(2023, 2, 16), as_arg=True)
    @mock.patch('telethon.TelegramClient', return_value=AsyncMock())
    async def test_telethon_service_cache(clock: FrozenDateTimeFactory, self: TestCase, mock_client):
        """ tests that get_entity function is called only once on sequential find_user and find_chat calls
            if entity is cached and its time limit is not reached """
        bobweb.bob.config.tg_client_api_id = '123'
        bobweb.bob.config.tg_client_api_hash = '456'
        # Before any calls, call count for get_entity should be 0
        await telethon_service.client.initialize_and_get_telethon_client()
        self.assertEqual(0, telethon_service.client._client.get_entity.call_count)
        self.assertEqual(0, len(telethon_service.client.user_ref_cache))

        # Now call find_user once. As the cache is empty, should call get_entity from
        # telegram client
        await telethon_service.client.find_user(123)
        self.assertEqual(1, telethon_service.client._client.get_entity.call_count)

        # Now if we call find_user again with same id, it is found from cache and no
        # Telegram API call is made
        await telethon_service.client.find_user(123)
        self.assertEqual(1, telethon_service.client._client.get_entity.call_count)

        self.assertIsNotNone(telethon_service.client.user_ref_cache[123])
        self.assertEqual(1, len(telethon_service.client.user_ref_cache))

        # If another user is requested, it requires Telegram API call
        await telethon_service.client.find_user(456)
        self.assertEqual(2, telethon_service.client._client.get_entity.call_count)
        # And cache size is increased by one
        self.assertEqual(2, len(telethon_service.client.user_ref_cache))

        # Now, if cache item is invalidated by time limit, get_entity from telegram client is called again.
        # Each _find_entity call invalidates all expired cache items. So after 1 day, new call should first
        # remove all existing expired items and then call get_entity
        clock.tick(datetime.timedelta(days=1))
        await telethon_service.client.find_user(123)
        self.assertEqual(3, telethon_service.client._client.get_entity.call_count)
        self.assertEqual(1, len(telethon_service.client.user_ref_cache))

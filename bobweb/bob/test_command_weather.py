import os

import django
import pytest
from django.core import management
from django.test import TestCase
from unittest import mock
from unittest.mock import Mock

from bobweb.bob import main
from bobweb.bob.command_weather import WeatherCommand
from bobweb.bob.resources.test.weather_mock_data import helsinki_weather, turku_weather
from bobweb.bob.tests_utils import assert_reply_to_contain, \
    assert_get_parameters_returns_expected_value, assert_command_triggers, mock_fetch_json_with_content
from bobweb.web.bobapp.models import ChatMember


async def mock_response_200_with_helsinki_weather(*args, **kwargs):
    return helsinki_weather

async def mock_response_200_with_turku_weather(*args, **kwargs):
    return turku_weather


@pytest.mark.asyncio
@mock.patch('os.getenv', lambda key: "DUMMY_VALUE_FOR_ENVIRONMENT_VARIABLE")
@mock.patch('bobweb.bob.async_http.fetch_json', mock_response_200_with_helsinki_weather)  # Default mock response
class WeatherCommandTest(django.test.TransactionTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super(WeatherCommandTest, cls).setUpClass()
        django.setup()
        management.call_command('migrate')

    async def test_command_triggers(self):
        should_trigger = ['/sää', '!sää', '.sää', '/SÄÄ', '/sää test', '/saa']
        should_not_trigger = ['sää', 'test /sää']
        await assert_command_triggers(self, WeatherCommand, should_trigger, should_not_trigger)

    async def test_get_given_parameter(self):
        assert_get_parameters_returns_expected_value(self, '!sää', WeatherCommand())

    async def test_should_contain_weather_data(self):
        await assert_reply_to_contain(self, '/sää helsinki', ['helsinki', 'UTC', 'tuntuu', 'm/s'])

    async def test_should_inform_if_city_not_found(self):
        # Does not use mock that raises error, as the real weather api has the
        # requst status code in the response payload json
        with mock.patch('bobweb.bob.async_http.fetch_json', mock_fetch_json_with_content({"cod": "404"})):
            await assert_reply_to_contain(self, '/sää asd', ['Kaupunkia ei löydy.'])

    async def test_new_user_no_parameter_should_reply_with_help(self):
        mock_chat_member = Mock(spec=ChatMember)
        mock_chat_member.latest_weather_city = None
        with mock.patch('bobweb.bob.database.get_chat_member', lambda *args, **kwargs: mock_chat_member):
            await assert_reply_to_contain(self, '/sää', ['Määrittele kaupunki kirjoittamalla se komennon perään.'])

    async def test_known_user_no_parameter_should_reply_with_users_last_city(self):
        mock_chat_member = Mock(spec=ChatMember)
        mock_chat_member.latest_weather_city = 'Turku'
        with mock.patch('bobweb.bob.database.get_chat_member', lambda *args, **kwargs: mock_chat_member):
            with mock.patch('bobweb.bob.async_http.fetch_json', mock_response_200_with_turku_weather):
                await assert_reply_to_contain(self, '/sää', ['tää on turku'])



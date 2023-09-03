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
    MockResponse, mock_response_with_code, assert_get_parameters_returns_expected_value, assert_command_triggers
from bobweb.web.bobapp.models import ChatMember


def mock_response_200_with_weather(*args, **kwargs):
    return MockResponse(status_code=200, content=helsinki_weather)


@pytest.mark.asyncio
@mock.patch('os.getenv', lambda key: "DUMMY_VALUE_FOR_ENVIRONMENT_VARIABLE")
@mock.patch('requests.get', mock_response_200_with_weather)  # Default mock response
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
        with mock.patch('requests.get', mock_response_with_code(404, {"cod": "404"})):
            await assert_reply_to_contain(self, '/sää asd', ['Kaupunkia ei löydy.'])

    async def test_new_user_no_parameter_should_reply_with_help(self):
        mock_chat_member = Mock(spec=ChatMember)
        mock_chat_member.latest_weather_city = None
        with mock.patch('bobweb.bob.database.get_chat_member', lambda *args, **kwargs: mock_chat_member):
            await assert_reply_to_contain(self, '/sää', ['Määrittele kaupunki kirjoittamalla se komennon perään.'])

    async def test_known_user_no_parameter_should_reply_with_users_last_city(self):
        mock_chat_member = Mock(spec=ChatMember)
        mock_chat_member.latest_weather_city = 'Turku'
        mock_response = MockResponse(content=turku_weather)
        with mock.patch('bobweb.bob.database.get_chat_member', lambda *args, **kwargs: mock_chat_member):
            with mock.patch('requests.get', lambda *args, **kwargs: mock_response):
                await assert_reply_to_contain(self, '/sää', ['tää on turku'])



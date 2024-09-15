import datetime
import os

import django
import pytest
from django.core import management
from django.test import TestCase
from unittest import mock
from unittest.mock import Mock

import bobweb
from bobweb.bob import main, config
from bobweb.bob.command_weather import WeatherCommand, WeatherData, format_scheduled_message_preview
from bobweb.bob.resources.bob_constants import DEFAULT_TIME_FORMAT
from bobweb.bob.resources.test.weather_mock_data import helsinki_weather, turku_weather
from bobweb.bob.tests_mocks_v2 import init_chat_user
from bobweb.bob.tests_utils import assert_reply_to_contain, \
    assert_get_parameters_returns_expected_value, assert_command_triggers, mock_async_get_json
from bobweb.web.bobapp.models import ChatMember


async def mock_response_200_with_helsinki_weather(*args, **kwargs):
    return helsinki_weather


async def mock_response_200_with_turku_weather(*args, **kwargs):
    return turku_weather


@pytest.mark.asyncio
@mock.patch('bobweb.bob.async_http.get_json', mock_response_200_with_helsinki_weather)  # Default mock response
class WeatherCommandTest(django.test.TransactionTestCase):
    mock_weather_api_key = 'DUMMY_VALUE_FOR_ENVIRONMENT_VARIABLE'

    @classmethod
    def setUpClass(cls) -> None:
        super(WeatherCommandTest, cls).setUpClass()
        django.setup()
        management.call_command('migrate')
        config.open_weather_api_key = cls.mock_weather_api_key

    async def test_command_triggers(self):
        should_trigger = ['/sää', '!sää', '.sää', '/SÄÄ', '/sää test', '/saa']
        should_not_trigger = ['sää', 'test /sää']
        await assert_command_triggers(self, WeatherCommand, should_trigger, should_not_trigger)

    async def test_get_given_parameter(self):
        assert_get_parameters_returns_expected_value(self, '!sää', WeatherCommand())

    async def test_should_raise_error_if_weather_api_key_is_missing(self):
        config.open_weather_api_key = None
        chat, user = init_chat_user()
        with self.assertRaises(EnvironmentError) as error_context:
            await user.send_message('/sää helsinki')
        self.assertEqual('OPEN_WEATHER_API_KEY is not set.', error_context.exception.args[0])
        config.open_weather_api_key = self.mock_weather_api_key

    async def test_should_contain_weather_data(self):
        await assert_reply_to_contain(self, '/sää helsinki', ['Helsinki', 'UTC', 'tuntuu', 'm/s'])

    async def test_should_inform_if_city_not_found(self):
        # Does not use mock that raises error, as the real weather api has the
        # requst status code in the response payload json
        with mock.patch('bobweb.bob.async_http.get_json', mock_async_get_json({"cod": "404"})):
            await assert_reply_to_contain(self, '/sää asd', ['Kaupunkia ei löydy.'])

    async def test_new_user_no_parameter_should_reply_with_help(self):
        mock_chat_member = Mock(spec=ChatMember)
        mock_chat_member.latest_weather_city = None
        with mock.patch('bobweb.bob.database.get_chat_member', lambda *args, **kwargs: mock_chat_member):
            await assert_reply_to_contain(self, '/sää', ['Määrittele kaupunki kirjoittamalla se komennon perään.'])

    async def test_known_user_no_parameter_should_reply_with_users_last_city(self):
        mock_chat_member = Mock(spec=ChatMember)
        mock_chat_member.latest_weather_city = 'Turku'
        with (mock.patch('bobweb.bob.database.get_chat_member', lambda *args, **kwargs: mock_chat_member),
              mock.patch('bobweb.bob.async_http.get_json', mock_response_200_with_turku_weather)):
            await assert_reply_to_contain(self, '/sää', ['tää on Turku'])

    async def test_results_is_formatted_as_expected(self):
        chat, user = init_chat_user()
        await user.send_message('/sää helsinki')

        # In test data the target city time zone time delta is 7200 seconds = 2 hours
        local_time_string = (datetime.datetime.utcnow() + datetime.timedelta(hours=2)).strftime(DEFAULT_TIME_FORMAT)
        expected_response = ('🇫🇮 Helsinki\n'
                             '🕒 ' + local_time_string + ' (UTC+02:00)\n'
                             '🌡 -0.6 °C (tuntuu -2.9 °C)\n'
                             '💨 1.79 m/s lounaasta\n'
                             '🌨 lumisadetta')
        self.assertEqual(expected_response, chat.last_bot_txt())

    #
    # Tests for message board weather feature
    #
    def test_message_board_weather_is_formatted_as_expected(self):
        data: WeatherData = WeatherData(
            city_row="🇫🇮 Helsinki",
            time_row="🕒 17:00 (UTC+02:00)",
            temperature_row="🌡 -0.6 °C (tuntuu -2.9 °C)",
            wind_row="💨 1.79 m/s lounaasta",
            weather_description_row="🌨 lumisadetta",
            sunrise_and_set_row="🌅 auringon nousu 07:55 🌃 lasku 18:45"
        )

        expected_format = ('🇫🇮 Helsinki\n'
                           '🌡 -0.6 °C (tuntuu -2.9 °C)\n'
                           '🌨 lumisadetta\n'
                           '💨 1.79 m/s lounaasta\n'
                           '🕒 17:00 (UTC+02:00)\n'
                           '🌅 auringon nousu 07:55 🌃 lasku 18:45')
        self.assertEqual(expected_format, format_scheduled_message_preview(data))

import asyncio
import datetime
import os
from typing import List

import django
import pytest
from aiohttp import ClientResponseError
from django.core import management
from django.test import TestCase
from unittest import mock
from unittest.mock import Mock, AsyncMock

from freezegun import freeze_time
from freezegun.api import FrozenDateTimeFactory

import bobweb
from bobweb.bob import main, config, command_weather
from bobweb.bob.command_weather import WeatherCommand, WeatherData, format_scheduled_message_preview, \
    WeatherMessageBoardMessage, create_weather_scheduled_message, parse_response_content_to_weather_data
from bobweb.bob.message_board import MessageBoard
from bobweb.bob.resources.bob_constants import DEFAULT_TIME_FORMAT
from bobweb.bob.resources.test.weather_mock_data import helsinki_weather, turku_weather
from bobweb.bob.tests_mocks_v2 import init_chat_user
from bobweb.bob.tests_utils import assert_reply_to_contain, \
    assert_get_parameters_returns_expected_value, assert_command_triggers, mock_async_get_json, \
    async_raise_client_response_error
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

    async def test_should_inform_if_response_404_not_found(self):
        # Real weather api might return response with 404 not found. If so, Should inform user that city was not found.
        with mock.patch('bobweb.bob.async_http.get_json', async_raise_client_response_error(404, 'not found')):
            await assert_reply_to_contain(self, '/sää asd', ['Kaupunkia ei löydy.'])

    async def test_should_inform_if_response_500_internal_server_error(self):
        # Weather api might return response with 500 internal server error when city is not found
        with mock.patch('bobweb.bob.async_http.get_json', async_raise_client_response_error(500, 'error')):
            await assert_reply_to_contain(self, '/sää asd', ['Kaupunkia ei löydy.'])

    async def test_should_raise_exception_if_error_code_other_than_predefined_not_found_cases(self):
        # If response is not 2xx ok AND is different error code than 404 not found or 500 internal server error,
        # the exception is raised
        with (mock.patch('bobweb.bob.async_http.get_json', async_raise_client_response_error(401, 'error')),
              self.assertRaises(ClientResponseError) as error_context):
            chat, user = init_chat_user()
            await user.send_message('/sää helsinki')
            self.assertEqual('error', error_context.exception.args[0])

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
        local_time_string = (datetime.datetime.now(datetime.timezone.utc)
                             + datetime.timedelta(hours=2)).strftime(DEFAULT_TIME_FORMAT)
        expected_response = ('🇫🇮 Helsinki\n'
                             '🕒 ' + local_time_string + ' (UTC+02:00)\n'
                                                        '🌡 -0.6 °C (tuntuu -2.9 °C)\n'
                                                        '💨 1.79 m/s lounaasta\n'
                                                        '🌨 lumisadetta')
        self.assertEqual(expected_response, chat.last_bot_txt())


mock_city_list = ['Helsinki', 'Tampere', 'Turku']


async def mock_fetch_and_parse_weather_data(city_parameter: str):
    weather_data = command_weather.parse_response_content_to_weather_data(helsinki_weather)
    weather_data.city_row = city_parameter
    return weather_data


async def create_mock_weather_message_with_city_list(city_list: List[str]):
    with mock.patch('bobweb.bob.database.get_latest_weather_cities_for_members_of_chat',
                    lambda *args, **kwargs: city_list):
        # This simple mock causes side effect, that the city names start with a lower character as the name
        # is not returned from the API result
        return await create_weather_scheduled_message(message_board=Mock(spec=MessageBoard), chat_id=1)


FULL_TICK = 0.005  # Seconds
HALF_TICK = FULL_TICK / 2


@pytest.mark.asyncio
@mock.patch('random.shuffle', lambda values: values)
class WeatherMessageBoardMessageTests(django.test.TransactionTestCase):
    mock_weather_api_key = 'DUMMY_VALUE_FOR_ENVIRONMENT_VARIABLE'

    @classmethod
    def setUpClass(cls) -> None:
        super(WeatherMessageBoardMessageTests, cls).setUpClass()
        django.setup()
        management.call_command('migrate')
        config.open_weather_api_key = cls.mock_weather_api_key
        # Delay of the board updates are set to be one full tick.
        WeatherMessageBoardMessage.city_change_delay_in_seconds = FULL_TICK

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

    async def test_init_no_cities(self):
        """ Verifies behavior when no _cities are retrieved from the database. """
        weather_message = await create_mock_weather_message_with_city_list([])

        self.assertEqual(WeatherMessageBoardMessage.no_cities_message, weather_message.body)
        self.assertEqual("", weather_message.preview)
        self.assertEqual(None, weather_message._update_task)

    @mock.patch('bobweb.bob.command_weather.fetch_and_parse_weather_data', mock_fetch_and_parse_weather_data)
    async def test_init_with_single_city(self):
        """ Ensures that only one update happens when there's a single city. """
        """ Tests initialization when _cities exist and ensures correct list setup. """
        weather_message = await create_mock_weather_message_with_city_list(['city A'])

        # As there is only one city, it is updated and no update task is started
        self.assertIn('city a', weather_message.body)
        self.assertEqual(None, weather_message._update_task)

    @mock.patch('bobweb.bob.command_weather.fetch_and_parse_weather_data', mock_fetch_and_parse_weather_data)
    async def test_init_with_cities(self):
        """ Tests initialization when _cities exist and ensures correct list setup. """
        weather_message = await create_mock_weather_message_with_city_list(mock_city_list)

        # As there are multiple choices, the first is updated
        self.assertIn('helsinki\n🌡 -0.6 °C (tuntuu -2.9 °C)', weather_message.body)
        self.assertNotEquals(None, weather_message._update_task)

    @mock.patch('bobweb.bob.command_weather.fetch_and_parse_weather_data', mock_fetch_and_parse_weather_data)
    async def test_cities_are_rotated(self):
        """ Tests multiple city updates with the loop. """
        weather_message = await create_mock_weather_message_with_city_list(mock_city_list)
        await asyncio.sleep(HALF_TICK)  # Offset tests timing with a half a tick with regarding the update task schedule
        self.assertIn('helsinki', weather_message.body)

        await asyncio.sleep(FULL_TICK)
        self.assertIn('tampere', weather_message.body)

        await asyncio.sleep(FULL_TICK)
        self.assertIn('turku', weather_message.body)

        # Rotates back to the first item
        await asyncio.sleep(FULL_TICK)
        self.assertIn('helsinki', weather_message.body)

        weather_message.schedule_set_to_end = True
        await asyncio.sleep(FULL_TICK)  # Wait for one tick
        self.assertEqual(True, weather_message._update_task.done())

    async def test_non_existing_city_is_removed_from_list(self):
        with mock.patch('bobweb.bob.async_http.get_json', async_raise_client_response_error(404, 'not found')):
            weather_message = await create_mock_weather_message_with_city_list(['city_that_is_not_found'])
        self.assertEqual(0, len(weather_message._cities))
        self.assertEqual(-1, weather_message.current_city_index)

    @freeze_time('2025-01-01 12:30', as_arg=True)
    @mock.patch('bobweb.bob.command_weather.fetch_and_parse_weather_data', new_callable=AsyncMock)
    async def test_find_weather_data_cache_hit(clock: FrozenDateTimeFactory, self, mock_function: AsyncMock):
        """ Verifies that the weather data cache is used correctly """
        WeatherMessageBoardMessage._weather_cache = {}
        mock_function.return_value = parse_response_content_to_weather_data(helsinki_weather)
        weather_message = await create_mock_weather_message_with_city_list(['helsinki'])
        self.assertEqual(1, mock_function.call_count)

        weather_data_from_cache = weather_message._weather_cache.get('helsinki')
        self.assertNotEquals(None, weather_data_from_cache)
        self.assertEqual(datetime.datetime(2025, 1, 1, 12, 30), weather_data_from_cache.created_at)

        # Now if we try to find weather data for helsinki again, it should be the same object as before and the actual
        # API fetch should have only been called once
        new_weather_fetch_result = await weather_message.find_weather_data('helsinki')
        self.assertEqual(weather_data_from_cache, new_weather_fetch_result)
        self.assertEqual(1, mock_function.call_count)

        # Now if we try to find data for another city, as it is not found from the cache, new fetch is done
        self.assertEqual(1, len(WeatherMessageBoardMessage._weather_cache))
        await weather_message.find_weather_data('test')
        self.assertEqual(2, mock_function.call_count)
        self.assertEqual(2, len(WeatherMessageBoardMessage._weather_cache))

        # Now, if we proceed time, the weather data has been invalidated and a new one is fetched
        clock.tick(datetime.timedelta(hours=1, minutes=1))
        mock_function.return_value = parse_response_content_to_weather_data(helsinki_weather)

        weather_after_an_hour = await weather_message.find_weather_data('helsinki')
        self.assertEqual(3, mock_function.call_count)
        self.assertEqual(datetime.datetime(2025, 1, 1, 13, 31), weather_after_an_hour.created_at)

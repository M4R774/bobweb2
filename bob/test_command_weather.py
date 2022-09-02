import os
from unittest import TestCase, mock

import main
from command_weather import WeatherCommand
from resources.test.weather_mock_data import helsinki_weather, turku_weather
from utils_test import assert_has_reply_to, assert_no_reply_to, assert_reply_contains, \
    MockResponse, mock_response_with_code, MockChatMember


def mock_response_200_with_weather(*args, **kwargs):
    return MockResponse(status_code=200, content=helsinki_weather)


@mock.patch('os.getenv', lambda key: "DUMMY_VALUE_FOR_ENVIRONMENT_VARIABLE")
@mock.patch('requests.get', mock_response_200_with_weather)  # Default mock response
class Test(TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        os.system("python ../web/manage.py migrate")

    def test_command_should_reply(self):
        assert_has_reply_to(self, '/sää')

    def test_no_prefix_no_reply(self):
        assert_no_reply_to(self, 'sää')

    def test_text_before_command_no_reply(self):
        assert_no_reply_to(self, 'test /sää')

    def test_text_after_command_should_reply(self):
        assert_has_reply_to(self, '/sää test')

    def test_should_contain_weather_data(self):
        assert_reply_contains(self, '/sää helsinki', ['helsinki', 'UTC', 'tuntuu', 'm/s'])

    def test_should_inform_if_city_not_found(self):
        with mock.patch('requests.get', mock_response_with_code(404, {"cod": "404"})):
            assert_reply_contains(self, '/sää', ['Kaupunkia ei löydy.'])

    def test_new_user_no_parameter_should_reply_with_help(self):
        with mock.patch('database.get_chat_member', lambda *args, **kwargs: MockChatMember()):
            assert_reply_contains(self, '/sää', ['Määrittele kaupunki kirjoittamalla se komennon perään.'])

    def test_known_user_no_parameter_should_reply_with_users_last_city(self):
        mock_chat_member = MockChatMember(latest_weather_city='Turku')
        mock_response = MockResponse(content=turku_weather)
        with mock.patch('database.get_chat_member', lambda *args, **kwargs: mock_chat_member):
            with mock.patch('requests.get', lambda *args, **kwargs: mock_response):
                assert_reply_contains(self, '/sää', ['tää on turku'])

    def test_get_given_parameter(self):
        message = '!sää test . test/test-test\ntest\ttest .vai test \n '
        parameter_expected = 'test . test/test-test\ntest\ttest .vai test'
        parameter_actual = WeatherCommand().get_parameters(message)
        self.assertEqual(parameter_expected, parameter_actual)

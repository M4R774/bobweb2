import datetime
import io
import json
import os

from unittest import mock
from django.test import TestCase
from unittest.mock import Mock, patch

import requests
from PIL.Image import Image
from requests import Response

from bobweb.bob import command_epic_games
from bobweb.bob.command_epic_games import epic_free_games_api_endpoint, EpicGamesOffersCommand
from bobweb.bob.test_command_kunta import create_mock_image
from bobweb.bob.tests_mocks_v2 import init_chat_user
from bobweb.bob.tests_utils import MockResponse, mock_response_with_code, assert_command_triggers


def mock_response_200_with_test_data(url: str, *args, **kwargs):
    if 'freeGamesPromotions' in url:
        # first api call that gets the promotion date
        with open('bobweb/bob/resources/test/epicGamesFreeGamesPromotionsExample.json') as example_json:
            mock_json_dict: dict = json.loads(example_json.read())
            return MockResponse(status_code=200, content=mock_json_dict)
    elif url.endswith('.png'):
        # Game offer image request -> Create a mock response with appropriate content
        img: Image = create_mock_image(*args, **kwargs)
        img_byte_array = io.BytesIO()
        img.save(img_byte_array, format='PNG')
        return MockResponse(status_code=200, content=img_byte_array.getvalue())


class EpicGamesApiEndpointPingTest(TestCase):
    # Smoke test against the real api
    def test_epic_games_api_endpoint_ok(self):
        res: Response = requests.get(epic_free_games_api_endpoint)
        self.assertEqual(200, res.status_code)


# By default, if nothing else is defined, all request.get requests are returned with this mock
@mock.patch('requests.get', mock_response_200_with_test_data)
class EpicGamesBehavioralTests(TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super(EpicGamesBehavioralTests, cls).setUpClass()
        os.system("python bobweb/web/manage.py migrate")
        EpicGamesOffersCommand.run_async = False

    def test_command_triggers(self):
        should_trigger = ['/epicgames', '!epicgames', '.epicgames', '/EPICGAMES']
        should_not_trigger = ['epicgames', 'test /epicgames', '/epicgames test']
        assert_command_triggers(self, EpicGamesOffersCommand, should_trigger, should_not_trigger)

    def test_should_return_expected_game_name_from_mock_data(self):
        chat, user = init_chat_user()
        user.send_message('/epicgames')
        self.assertIn('Epistory - Typing Chronicles', chat.last_bot_txt())

    def test_should_inform_if_fetch_failed(self):
        with mock.patch('requests.get', mock_response_with_code(404)):
            chat, user = init_chat_user()
            user.send_message('/epicgames')
            self.assertIn(command_epic_games.fetch_failed_msg, chat.last_bot_txt())

    def test_should_inform_if_response_ok_but_no_free_games(self):
        with mock.patch('requests.get', mock_response_with_code(200, {})):
            chat, user = init_chat_user()
            user.send_message('/epicgames')
            self.assertIn(command_epic_games.fetch_ok_no_free_games, chat.last_bot_txt())

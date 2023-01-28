import datetime
import io
import json
import os

from unittest import mock
from django.test import TestCase
from unittest.mock import Mock, patch

import requests
from PIL.Image import Image
from freezegun import freeze_time
from freezegun.api import TickingDateTimeFactory
from requests import Response

import bobweb.bob.epic_games
from bobweb.bob import main, epic_games, command_service
from bobweb.bob.epic_games import epic_free_games_api_endpoint, EpicGamesOffersCommand
from bobweb.bob.test_command_kunta import create_mock_image
from bobweb.bob.tests_mocks_v2 import init_chat_user, MockUser, MockChat
from bobweb.bob.tests_utils import MockResponse, assert_has_reply_to, assert_no_reply_to, assert_has_reply_to_v2, \
    assert_no_reply_to_v2


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


# By default, if nothing else is defined, all request.get requests are returned with this mock
@mock.patch('requests.get', mock_response_200_with_test_data)
class Test(TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super(Test, cls).setUpClass()
        os.system("python bobweb/web/manage.py migrate")
        EpicGamesOffersCommand.run_async = False

    # Easy way to replace a class method with a predefined or plain Mock object
    # More info: #https://docs.python.org/3/library/unittest.mock.html#patch-object
    @patch.object(bobweb.bob.epic_games.EpicGamesOffersCommand, 'handle_update')
    def test_command_triggers(self, mock_handle_update_method: Mock):
        user = MockUser(chat=MockChat())
        # Cases that should trigger
        user.send_message('/epicgames')
        user.send_message('/epicGAMES')
        # Cases that should not trigger
        user.send_message('epicgames')
        user.send_message('test /epicgames')
        user.send_message('/epicgames test')

        self.assertEqual(2, mock_handle_update_method.call_count)


    def test_should_return_expected_game_name_from_mock_data(self):
        chat, user = init_chat_user()
        user.send_message('/epicgames')
        self.assertIn('Epistory - Typing Chronicles', chat.last_bot_txt())

    # Smoke test against the real api
    @mock.patch('requests.get', requests.get)
    def test_epic_games_api_endpoint_ok(self):
        res: Response = requests.get(epic_free_games_api_endpoint)
        self.assertEqual(200, res.status_code)

    @freeze_time(datetime.datetime(2023, 1, 1, 18, 59, 59, 999), tick=True, as_kwarg='clock')
    def test_timed_epic_games_cron_job_triggers(self, clock: TickingDateTimeFactory):
        pass

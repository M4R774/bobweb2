import json
import os

from unittest import IsolatedAsyncioTestCase, mock


from bobweb.bob import main, epic_games
from bobweb.bob.tests_utils import MockResponse

import django

os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    "bobweb.web.web.settings"
)

os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"
django.setup()


def mock_response_200_with_test_data(*args, **kwargs):
    with open('resources/test/epicGamesFreeGamesPromotionsExample.json') as example_json:
        mock_json_dict: dict = json.loads(example_json.read())
        return MockResponse(status_code=200, content=mock_json_dict)


# By default, if nothing else is defined, all request.get requests are returned with this mock
@mock.patch('requests.get', mock_response_200_with_test_data)
class Test(IsolatedAsyncioTestCase):

    def test_fetch(self):
        epic_games.create_free_games_announcement_msg()

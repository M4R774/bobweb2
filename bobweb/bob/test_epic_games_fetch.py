import json
import os

from unittest import IsolatedAsyncioTestCase, mock


from bobweb.bob import main, scheduler
from bobweb.bob.tests_utils import MockResponse

import django

os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    "bobweb.web.web.settings"
)

os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"
django.setup()


def mock_response_200_with_test_data(*args, **kwargs):
    mock_json_dict: dict = json.loads(open('resources/test/epicGamesFreeGamesPromotionsExample.json').read())
    return MockResponse(status_code=200, content=mock_json_dict)


# By default, if nothing else is defined, all request.get requests are returned with this mock
@mock.patch('requests.get', mock_response_200_with_test_data)
class Test(IsolatedAsyncioTestCase):

    def test_fetch(self):
        scheduler.fetch_free_epic_games_offering()

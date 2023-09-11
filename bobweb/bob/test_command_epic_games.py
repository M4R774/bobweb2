import io
import json
from typing import List

from unittest import mock

import django
import pytest
from django.core import management
from django.test import TestCase
from unittest.mock import Mock, patch

import requests
from PIL.Image import Image
from requests import Response

from bobweb.bob import command_epic_games
from bobweb.bob.command_epic_games import epic_free_games_api_endpoint, EpicGamesOffersCommand, \
    get_product_page_or_deals_page_url
from bobweb.bob.test_command_kunta import create_mock_image
from bobweb.bob.tests_mocks_v2 import init_chat_user
from bobweb.bob.tests_utils import assert_command_triggers, mock_fetch_json_raises_error, mock_fetch_json_with_content


async def mock_fetch_json(urls: str, *args, **kwargs):
    if 'freeGamesPromotions' in urls:
        # first api call that gets the promotion date
        with open('bobweb/bob/resources/test/epicGamesFreeGamesPromotionsExample.json') as example_json:
            return json.loads(example_json.read())
    elif urls.endswith('.png'):
        # Game offer image request -> Create a mock response with appropriate content
        img: Image = create_mock_image(*args, **kwargs)
        img_byte_array = io.BytesIO()
        img.save(img_byte_array, format='PNG')
        return img_byte_array.getvalue()


async def mock_fetch_all_content_bytes(urls: List[str], *args, **kwargs):
    return [await mock_fetch_json(url) for url in urls]


class EpicGamesApiEndpointPingTest(TestCase):
    """ Smoke test against the real api """
    async def test_epic_games_api_endpoint_ok(self):
        res: Response = requests.get(epic_free_games_api_endpoint)  # Synchronous requests-library call is OK here
        self.assertEqual(200, res.status_code)


# By default, if nothing else is defined, all request.get requests are returned with this mock
@pytest.mark.asyncio
@mock.patch('bobweb.bob.async_http.fetch_json', mock_fetch_json)
@mock.patch('bobweb.bob.async_http.fetch_all_content_bytes', mock_fetch_all_content_bytes)
class EpicGamesBehavioralTests(django.test.TransactionTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super(EpicGamesBehavioralTests, cls).setUpClass()
        management.call_command('migrate')

    async def test_command_triggers(self):
        should_trigger = ['/epicgames', '!epicgames', '.epicgames', '/EPICGAMES']
        should_not_trigger = ['epicgames', 'test /epicgames', '/epicgames test']
        await assert_command_triggers(self, EpicGamesOffersCommand, should_trigger, should_not_trigger)

    async def test_should_return_expected_game_name_from_mock_data(self):
        chat, user = init_chat_user()
        await user.send_message('/epicgames')
        self.assertIn('Epistory - Typing Chronicles', chat.last_bot_txt())

    async def test_should_inform_if_fetch_failed(self):
        with mock.patch('bobweb.bob.async_http.fetch_json', mock_fetch_json_raises_error(404)):
            chat, user = init_chat_user()
            await user.send_message('/epicgames')
            self.assertIn(command_epic_games.fetch_failed_msg, chat.last_bot_txt())

    async def test_should_inform_if_response_ok_but_no_free_games(self):
        with mock.patch('bobweb.bob.async_http.fetch_json', mock_fetch_json_with_content({})):
            chat, user = init_chat_user()
            await user.send_message('/epicgames')
            self.assertIn(command_epic_games.fetch_ok_no_free_games, chat.last_bot_txt())

    async def test_get_product_page_or_deals_page_url(self):
        expected = 'https://store.epicgames.com/en-US/p/epistory-typing-chronicles-445794'
        actual = get_product_page_or_deals_page_url('epistory-typing-chronicles-445794')
        self.assertEqual(expected, actual)

        expected = 'https://store.epicgames.com/en-US/free-games'
        actual = get_product_page_or_deals_page_url(None)
        self.assertEqual(expected, actual)
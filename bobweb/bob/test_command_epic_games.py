import asyncio
import io
import json
from typing import List

from unittest import mock

import django
import pytest
from aiohttp import ClientResponseError
from django.core import management
from django.test import TestCase
from unittest.mock import Mock

import requests
from PIL.Image import Image
from freezegun import freeze_time
from requests import Response
from telegram.constants import ParseMode
from telegram.ext import CallbackContext

from bobweb.bob import command_epic_games, database
from bobweb.bob.command_epic_games import epic_free_games_api_endpoint, EpicGamesOffersCommand, \
    get_product_page_or_deals_page_url, daily_announce_new_free_epic_games_store_games
from bobweb.bob.test_command_kunta import create_mock_image
from bobweb.bob.tests_mocks_v2 import init_chat_user
from bobweb.bob.tests_utils import assert_command_triggers, mock_async_request_raises_client_response_error, \
    mock_async_get_json, AsyncMock


async def mock_fetch_json(url: str, *args, **kwargs):
    if 'freeGamesPromotions' in url:
        # first api call that gets the promotion date
        with open('bobweb/bob/resources/test/epicGamesFreeGamesPromotionsExample.json') as example_json:
            return json.loads(example_json.read())
    elif url.endswith('.png'):
        # Game offer image request -> Create a mock response with appropriate content
        img: Image = create_mock_image(*args, **kwargs)
        img_byte_array = io.BytesIO()
        img.save(img_byte_array, format='PNG')
        return img_byte_array.getvalue()


async def mock_fetch_all_content_bytes(urls: List[str], *args, **kwargs):
    return [await mock_fetch_json(url) for url in urls]


async def mock_fetch_raises_client_response_error(*args, **kwargs):
    raise ClientResponseError(status=-1, message='-1', headers={'a': 1}, request_info=None, history=None)


async def mock_fetch_raises_base_exception(*args, **kwargs):
    raise Exception('error_msg')


class MockApi:
    """ Mock api that only returns requested response at third call """
    call_count = 0

    async def mock_fetch_succeed_on_third_call(*args, **kwargs):
        MockApi.call_count += 1
        if MockApi.call_count >= 3:
            return await mock_fetch_json(*args, **kwargs)
        else:
            return await mock_fetch_raises_client_response_error(*args, **kwargs)


class EpicGamesApiEndpointPingTest(TestCase):
    """ Smoke test against the real api """

    async def test_epic_games_api_endpoint_ok(self):
        res: Response = requests.get(epic_free_games_api_endpoint)  # Synchronous requests-library call is OK here
        self.assertEqual(200, res.status_code)


# By default, if nothing else is defined, all request.get requests are returned with this mock
@pytest.mark.asyncio
@freeze_time('2023-01-20')  # Date on which there is a starting free game promotion in the test data
@mock.patch('bobweb.bob.async_http.get_json', mock_fetch_json)
@mock.patch('bobweb.bob.async_http.get_all_content_bytes_concurrently', mock_fetch_all_content_bytes)
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

    async def test_should_have_parse_mode_set_to_html_and_contains_html_links(self):
        chat, user = init_chat_user()
        await user.send_message('/epicgames')
        self.assertEqual(ParseMode.HTML, chat.last_bot_msg().parse_mode)
        self.assertIn('<a href="', chat.last_bot_txt())

    async def test_should_inform_if_fetch_failed(self):
        with mock.patch('bobweb.bob.async_http.get_json', mock_async_request_raises_client_response_error(404)):
            chat, user = init_chat_user()
            await user.send_message('/epicgames')
            self.assertIn(command_epic_games.fetch_failed_no_connection_msg, chat.last_bot_txt())

    async def test_should_inform_if_response_ok_but_no_free_games(self):
        with mock.patch('bobweb.bob.async_http.get_json', mock_async_get_json({})):
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


@pytest.mark.asyncio
@mock.patch('asyncio.sleep', new_callable=AsyncMock)
@mock.patch('bobweb.bob.async_http.get_json', mock_fetch_json)
@mock.patch('bobweb.bob.async_http.get_all_content_bytes_concurrently', mock_fetch_all_content_bytes)
class EpicGamesDailyAnnounceTests(django.test.TransactionTestCase):
    chat = None
    cb = None

    @classmethod
    def setUpClass(cls) -> None:
        super(EpicGamesDailyAnnounceTests, cls).setUpClass()
        management.call_command('migrate')

    def setUp(self):
        chat, user = init_chat_user()
        asyncio.run(user.send_message('hi'))
        chat_in_db = database.get_chat(chat.id)
        chat_in_db.free_game_offers_enabled = True
        chat_in_db.save()

        cb: CallbackContext = Mock(spec=CallbackContext)
        cb.bot = chat.bot

        self.chat = chat
        self.cb = cb

    @freeze_time('2023-01-01')
    async def test_no_new_offers_not_thursday(self, _):
        with self.assertLogs(level='INFO') as log:
            await daily_announce_new_free_epic_games_store_games(self.cb)
            self.assertIn('status fetched successfully but no new free games found', log.output[-1])

            # No messages as it's not thursday
            self.assertEqual([], self.chat.bot.messages)

    @freeze_time('2023-01-05')
    async def test_no_new_offers_its_thursday(self, _):
        with self.assertLogs(level='INFO') as log:
            await daily_announce_new_free_epic_games_store_games(self.cb)
            self.assertIn('status fetched successfully but no new free games found', log.output[-1])

            # Should have message, as it is expected to have new offers on thursday
            self.assertEqual('Uusia ilmaisia eeppisiä pelejä ei ole tällä hetkellä tarjolla 👾', self.chat.last_bot_txt())

    @freeze_time('2023-01-01')
    async def test_api_get_request_is_called_repeatedly_if_it_fails(self, sleep_mock):
        asyncio_fetch_mock = AsyncMock()
        asyncio_fetch_mock.return_value = await mock_fetch_json('freeGamesPromotions')
        with mock.patch('bobweb.bob.async_http.get_json', asyncio_fetch_mock) as fetch_mock:
            await daily_announce_new_free_epic_games_store_games(self.cb)
            # Fetch is expected to be called 5 times as
            self.assertEqual(5, fetch_mock.call_count)
            # And sleep should have been called 4 times with parameter of 60 seconds
            self.assertEqual(4, sleep_mock.call_count)
            self.assertEqual(60, sleep_mock.mock_calls[-1].args[-1])

    async def test_client_response_error(self, _):
        with (
            self.assertLogs(level='ERROR') as log,
            mock.patch('bobweb.bob.async_http.get_json', mock_fetch_raises_client_response_error)
        ):
            await daily_announce_new_free_epic_games_store_games(self.cb)
            # Should log an error to log and give user-friendly notification that fetch has failed
            self.assertIn('Epic Games Api error. [status]: -1, [message]: -1, [headers]: {\'a\': 1}', log.output[-1])
            self.assertIn('ei onnistuttu muodostamaan yhteyttä', self.chat.last_bot_txt())

    async def test_any_error_without_catch(self, _):
        with (
            self.assertLogs(level='ERROR') as log,
            mock.patch('bobweb.bob.async_http.get_json', mock_fetch_raises_base_exception)
        ):
            await daily_announce_new_free_epic_games_store_games(self.cb)
            self.assertIn('Epic Games error: error_msg', log.output[-1])
            self.assertIn('haku tai tietojen prosessointi epäonnistui', self.chat.last_bot_txt())

    @freeze_time('2023-01-19 16:05')  # Date on which there is a starting free game promotion in the test data
    async def test_fetch_succeeds_on_third_try(self, _):
        mock_api = MockApi
        with (
            mock.patch('bobweb.bob.async_http.get_json', mock_api.mock_fetch_succeed_on_third_call),
            self.assertNoLogs(logger=command_epic_games.logger)  # And there are no messages logged
        ):
            await daily_announce_new_free_epic_games_store_games(self.cb)
            # Check that expected game name is in response
            self.assertIn('Epistory - Typing Chronicles', self.chat.last_bot_txt())
            # Mock api has been called only three times, as the third time succeeds
            self.assertEqual(3, mock_api.call_count)

    @freeze_time('2023-01-19 16:05')  # Date on which there is a starting free game promotion in the test data
    async def test_should_have_parse_mode_set_to_html_and_contains_html_links(self, _):
        await daily_announce_new_free_epic_games_store_games(self.cb)
        self.assertEqual(ParseMode.HTML, self.chat.last_bot_msg().parse_mode)
        self.assertIn('<a href="', self.chat.last_bot_txt())

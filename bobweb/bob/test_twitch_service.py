import datetime
from unittest import mock

import django
import pytest
from django.core import management
from django.test import TestCase
from freezegun import freeze_time

from bobweb.bob import twitch_service, config
from bobweb.bob.tests_utils import async_raise_client_response_error, AsyncMock
from bobweb.bob.twitch_service import StreamStatus, extract_twitch_channel_url

twitch_stream_mock_response = """
{
    "data": [
        {
            "id": "1",
            "user_id": "2",
            "user_login": "twitchdev",
            "user_name": "TwitchDev",
            "game_id": "3",
            "game_name": "python",
            "type": "live",
            "title": "stream title",
            "viewer_count": 999,
            "started_at": "2024-01-01T12:00:00Z",
            "language": "en",
            "thumbnail_url": "https://static-cdn.jtvnw.net/previews-ttv/twitchdev-{width}x{height}.jpg",
            "tag_ids": [],
            "tags": [
                "twitch",
                "dev"
            ],
            "is_mature": false
        }
    ],
    "pagination": {
        "cursor": "eyJiIjp7IkN1cnNvciI6ImV5SnpJam96TnpjdU56YzJPRGsyT1RjeE5qa3hOaXdpWkNJNlptRnNjMlVzSW5RaU9uUnlkV1Y5In0sImEiOnsiQ3Vyc29yIjoiIn19"
    }
}
"""


@pytest.mark.asyncio
class TwitchServiceTests(django.test.TransactionTestCase):

    @classmethod
    def setUpClass(cls) -> None:
        super(TwitchServiceTests, cls).setUpClass()
        management.call_command('migrate')

    async def test_service_startup(self):
        async def mock_get_token(*args, **kwargs):
            # First call returns an access_token, second one returns None. Check for access token status
            if not args:
                self.assertEqual(None, twitch_service.instance.access_token)
                return '123'
            self.assertEqual('123', twitch_service.instance.access_token)
            return None

        config.twitch_client_api_id = 'A'
        config.twitch_client_api_secret = 'B'
        twitch_service.instance.access_token = None

        async_mock = AsyncMock()
        async_mock.return_value = await mock_get_token()
        with (
            mock.patch('bobweb.bob.twitch_service.validate_access_token_request_new_if_required', mock_get_token),
            mock.patch('asyncio.sleep', new_callable=AsyncMock)
        ):
            await twitch_service.start_service()

        # Clear after
        config.twitch_client_api_id = None
        config.twitch_client_api_secret = None
        twitch_service.instance.access_token = None

    def test_extract_twitch_channel_url(self):
        self.assertEqual('twitchdev', extract_twitch_channel_url('test https://www.twitch.tv/twitchdev test'))
        self.assertEqual('twitchdev', extract_twitch_channel_url('test https://twitch.tv/twitchdev test'))
        self.assertEqual('twitchdev', extract_twitch_channel_url('test http://twitch.tv/twitchdev test'))
        self.assertEqual('twitchdev', extract_twitch_channel_url('test twitch.tv/twitchdev test'))

        self.assertEqual(None, extract_twitch_channel_url('test twitch.tv test'))
        # dot before the link
        self.assertEqual(None, extract_twitch_channel_url('test .twitch.tv test'))
        # wrong protocol
        self.assertEqual(None, extract_twitch_channel_url('test sftp.twitch.tv/twitchdev test'))
        # malformed url
        self.assertEqual(None, extract_twitch_channel_url('test httttps://twitch.tv/twitchdev test'))
        # not a url
        self.assertEqual(None, extract_twitch_channel_url('test twitch/twitchdev test'))

    # To assure that the stream status is formatted to message as expected
    @freeze_time(datetime.datetime(2024, 1, 1, 12, 30, 0))
    def test_StreamStatus_to_message_with_html_parse_mode(self):
        # Create stream status object with only values that affect the time output
        status = StreamStatus(user_login='twitchtv',
                              user_name='TwitchTv',
                              stream_is_live=True)

        # When stream is live, should have only the time when the stream has started
        status.started_at_utc = datetime.datetime(2024, 1, 1, 12, 30, 0)
        self.assertIn('🕒 Striimi alkanut: klo 14:30', status.to_message_with_html_parse_mode())

        # If stream has started on a different day other than today, should have time when the stream started
        status.started_at_utc = datetime.datetime(2024, 1, 2, 12, 30, 0)
        self.assertIn('🕒 Striimi alkanut: 2.1.2024 klo 14:30', status.to_message_with_html_parse_mode())

        # Now if the stream has ended
        status.stream_is_live = False

        # Stream has ended on the same day
        status.started_at_utc = datetime.datetime(2024, 1, 1, 12, 30, 0)
        status.ended_at_utc = datetime.datetime(2024, 1, 1, 14, 0, 0)
        self.assertIn('🕒 Striimattu: klo 14:30 - 16:00', status.to_message_with_html_parse_mode())

        # And if the stream has ended and the stream started and ended on a different date, should have time with dates
        status.started_at_utc = datetime.datetime(2024, 1, 1, 12, 30, 0)
        status.ended_at_utc = datetime.datetime(2024, 1, 2, 14, 0, 0)
        self.assertIn('🕒 Striimattu: 1.1.2024 klo 14:30 - 2.1.2024 klo 16:00', status.to_message_with_html_parse_mode())

    @freeze_time("2024-01-01")
    def test_StreamStatus_object_is_updated_from_other_as_expected(self):
        empty_status = StreamStatus(user_login='twitchtv', stream_is_live=False)

        self.assertEqual(datetime.datetime(2024, 1, 1).date(), empty_status.updated_at.date())
        self.assertIsNone(empty_status.stream_title)
        self.assertIsNone(empty_status.game_name)
        self.assertIsNone(empty_status.viewer_count)

        new_status = StreamStatus(user_login='twitchtv',
                                  stream_is_live=False,
                                  stream_title='stream title',
                                  game_name='python',
                                  viewer_count=999)
        with freeze_time("2024-02-02"):
            empty_status.update_from(new_status)

        self.assertEqual(datetime.datetime(2024, 2, 2).date(), empty_status.updated_at.date())
        self.assertEqual('stream title', empty_status.stream_title)
        self.assertEqual('python', empty_status.game_name)
        self.assertEqual(999, empty_status.viewer_count)

    async def test_fetch_stream_status(self):
        # When instance has no access_token and fetch_stream_status is called,
        # it first tries to fetch a new access token and after that it tries to fetch stream status again
        twitch_service.instance.access_token = 'token'
        with (
            # Mock implementation that raises an exception
            mock.patch('bobweb.bob.async_http.get_json', async_raise_client_response_error(status=999)),
            self.assertRaises(Exception) as error_context,
            self.assertLogs(level='ERROR') as log
        ):
            await twitch_service.fetch_stream_status('twitchdev')
            self.assertIn('Failed to get stream status for twitchdev. Request returned with response code 999',
                          log.output[0])
            self.assertEqual('', error_context.exception.args[0])
        twitch_service.instance.access_token = None



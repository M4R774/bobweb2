import asyncio
import logging
import os
import re
import subprocess
from datetime import datetime
from typing import Optional, Tuple

from django.utils import html
import pytz
import streamlink
from aiohttp import ClientResponse, ClientResponseError
from six import BytesIO
from streamlink.plugins.twitch import TwitchHLSStream, TwitchHLSStreamReader

from bobweb.bob import config, utils_common, async_http
from bobweb.bob.config import twitch_api_access_token_env_var_name
from bobweb.bob.resources.bob_constants import FINNISH_DATE_TIME_FORMAT
from bobweb.bob.utils_common import MessageBuilder

logger = logging.getLogger(__name__)


# Pattern that matches Twitch channel link. 'https' and 'www' are optional, so twitch.tv/1234 is matched
twitch_channel_link_url_regex_pattern = r'(?:https?://)?(?:www\.)?twitch\.tv/([a-zA-Z0-9_]{4,25})'
streamlink_stream_type_best = 'best'


class StreamStatus:
    def __init__(self,
                 user_login: str,
                 stream_is_live: bool,
                 user_name: str = None,
                 created_at: datetime = None,
                 game_name: str = None,
                 stream_title: str = None,
                 viewer_count: int = None,
                 started_at: datetime = None,
                 # Thumbnail_url is used for
                 thumbnail_url: str = None):
        self.created_at = created_at or datetime.now(tz=pytz.utc)  # UTC
        # user_login is same as url slug. Only lowercase.
        self.user_login = user_login
        self.stream_is_live = stream_is_live
        # same as user_login, but with uppercase characters. Stored separately just for the
        # rare case if users name can be changed to differ from login / url slug
        self.user_name = user_name
        self.game_name = game_name
        self.stream_title = stream_title
        self.viewer_count = viewer_count
        self.started_at_utc = started_at  # UTC
        # After base url image width and heigh is given
        # For example: 'https://static-cdn.jtvnw.net/previews-ttv/live_user_{channel_name}-{width}x{height}.jpg'
        # Used for getting the initial stream status message quickly
        self.thumbnail_url = thumbnail_url
        # Stream video url is initially undefined. Is determined when the first frame update
        # is fetched. Lazily evaluated.
        self.stream_video_url = None

    def to_message_with_html_parse_mode(self):
        # All text received from twitch have to be html escaped
        started_at_localized_str = ''
        if self.started_at_utc:
            started_at_fi_tz = utils_common.fitz_from(self.started_at_utc)
            started_at_localized_str = started_at_fi_tz.strftime(FINNISH_DATE_TIME_FORMAT)

        channel_link = f'<a href="www.twitch.tv/{self.user_login}">twitch.tv/{self.user_login}</a>'
        if self.stream_is_live:
            heading = f'<b>🔴 {html.escape(self.user_name)} on LIVE! 🔴</b>'
        else:
            heading = f'<b>Kanavan {html.escape(self.user_name)} striimi on päättynyt 🏁</b>'

        return (MessageBuilder(heading)
                .append_to_new_line(html.escape(self.stream_title), '<i>', '</i>')
                .append_raw('\n')  # Always empty line after header and description
                .append_to_new_line(html.escape(self.game_name), '🎮 Peli: ')
                .append_to_new_line(self.viewer_count, '👀 Katsojia: ')
                .append_to_new_line(started_at_localized_str, '🕒 Striimi alkanut: ')
                .append_raw('\n')  # Always empty line before link
                .append_to_new_line(f'Katso livenä! {channel_link}')
                ).message


class TwitchServiceAuthError(Exception):
    """ Error for when authorization fails with Twitch servers """
    def __init__(self, *args: object) -> None:
        super().__init__(*args)


class TwitchService:
    """
    Class for Twitch service integrations.
    """
    def __init__(self, access_token: str = None):
        self.access_token: Optional[str] = access_token
        self.streamlink_client: streamlink.Streamlink = streamlink.Streamlink()

    async def start_service(self):
        # Check if current access token is valid
        self.access_token: Optional[str] = await validate_access_token_request_new_if_required()

        # Start hourly token validation cycle as per Twitch requirements. From the documentation:
        # "Any third-party app that calls the Twitch APIs and maintains an OAuth session must call the /validate
        # endpoint to verify that the access token is still valid. This includes web apps, mobile apps, desktop apps,
        # extensions, and chatbots. Your app must validate the OAuth token when it starts and on an hourly basis
        # thereafter."
        # Source: https://dev.twitch.tv/docs/authentication/validate-tokens/
        while self.access_token is not None:
            # Sleep for an hour and then validate the token
            await asyncio.sleep(60 * 60)
            await validate_access_token_request_new_if_required(self.access_token)


# Singleton instance
instance = TwitchService()


async def validate_access_token_request_new_if_required(current_access_token: str = None) -> Optional[str]:
    """
    Validates current access token or requires new if current has been invalidated
    :param current_access_token: if empy, current token is fetched from env variables
    :return: new token or None if token request failed or new token was rejected
    """
    if current_access_token is None:
        current_access_token = os.getenv(twitch_api_access_token_env_var_name)

    token_ok = await _is_access_token_valid(current_access_token)
    if not token_ok:
        try:
            # Replace current access token with a new one
            current_access_token = await _get_new_access_token()
            if current_access_token is not None:
                # Update access token to env variables
                os.environ[twitch_api_access_token_env_var_name] = current_access_token
        except ClientResponseError as e:
            logger.error(msg='Failed to get new Twitch Client Api access token. Twitch integration is now disabled',
                         exc_info=e)
            return None

    return current_access_token


async def _get_new_access_token() -> Optional[str]:
    """
    Fetches new access token from Twtich. If client api id and / or secret are missing, returns None and logs error
    :return: new access token
    """
    if not config.twitch_client_api_id or not config.twitch_client_api_secret:
        logger.error('Twitch client credentials are not configured, check your env variables. '
                       'Twitch integration is now disabled')
        return None

    # https://dev.twitch.tv/docs/authentication/getting-tokens-oauth/#client-credentials-grant-flow
    url = 'https://id.twitch.tv/oauth2/token'
    params = {
        'client_id': config.twitch_client_api_id,
        'client_secret': config.twitch_client_api_secret,
        # client_credentials are used as they do not require additional login by any user
        'grant_type': 'client_credentials'
    }
    data = await async_http.post_expect_json(url, params=params)
    return data.get('access_token')


async def _is_access_token_valid(access_token: str) -> bool:
    """
    Checks if given access token is valid
    :param access_token:
    :return: true, if valid
    """
    # https://dev.twitch.tv/docs/authentication/validate-tokens/
    url = 'https://id.twitch.tv/oauth2/validate'
    headers = {'Authorization': f'OAuth {access_token}'}
    response = await async_http.get(url, headers=headers)
    return response.ok


def extract_twitch_channel_url(text: str) -> Tuple[bool, Optional[str]]:
    # Regular expression pattern to match Twitch channel links
    match = re.search(twitch_channel_link_url_regex_pattern, text)
    if match:
        return True, match.group(1)
    else:
        return False, None


# Step 3: Make API request to get stream info
async def get_stream_status(channel_name: str) -> Optional[StreamStatus]:
    """
    Gets stream status for given channel. Raises exception, if twitch api access token has been invalidated or request
    fails for other reason. If request fails with status code 401, access token is tried to be refreshed.
    :param channel_name:
    :return: returns stream status if request to twitch was successful. If request fails or bot has not received valid
             access token returns None
    """
    if not instance.access_token:
        logger.error('No Twitch access token. Twitch integration is now disabled')
        return None

    # https://dev.twitch.tv/docs/api/reference/#get-streams
    url = f'https://api.twitch.tv/helix/streams'
    headers = {
        'Client-Id': config.twitch_client_api_id,
        'Authorization': f'Bearer {instance.access_token}'
    }
    params = {'user_login': channel_name}

    try:
        response_dict = await async_http.get_json(url, headers=headers, params=params)
    except ClientResponse as e:
        logger.error(f'Failed to get stream status for {channel_name}. Request retuned with response code {e.status}')
        # Try to renew the token and then try to get stream info again once! If service restart fails,
        # no access token is set and the recall will raise error at the first check
        if e.status == 401:
            await instance.start_service()
            return await get_stream_status(channel_name)
        else:
            raise e  # In other cases, just raise the original exception

    stream_list = response_dict['data']
    if not stream_list:
        return StreamStatus(user_login=channel_name, stream_is_live=False)

    return parse_stream_status_from_stream_response(stream_list[0])


def parse_stream_status_from_stream_response(data: dict) -> StreamStatus:
    started_at_str = data['started_at']
    date_time_format = '%Y-%m-%dT%H:%M:%SZ'
    started_at_dt = utils_common.strptime_or_none(started_at_str, date_time_format)
    return StreamStatus(
        user_login=data['user_login'],
        user_name=data['user_name'],
        stream_is_live=True,
        game_name=data['game_name'],
        stream_title=data['title'],
        viewer_count=data['viewer_count'],
        started_at=started_at_dt,
        thumbnail_url=data['thumbnail_url']
    )


def capture_frame(stream_status: StreamStatus) -> bytes:
    twitch_url = "https://www.twitch.tv/" + stream_status.user_login
    available_streams: TwitchHLSStream = instance.streamlink_client.streams(twitch_url)
    stream: TwitchHLSStream = available_streams[streamlink_stream_type_best]
    stream.disable_ads = True
    stream_reader: TwitchHLSStreamReader = stream.open()

    # Instead of writing to a temp file, let's use an in-memory buffer
    buffer = BytesIO()

    # Read enough bytes to ensure getting a full key frame:
    # This value could be adjusted based on the stream's bitrate
    buffer.write(stream_reader.read(1024 * 256))

    # Prepare ffmpeg command using a pipe
    command = [
        'ffmpeg',
        '-i', 'pipe:0',  # Use stdin for input
        '-frames:v', '1',  # Get only one frame
        '-f', 'image2pipe',  # Output to a pipe
        '-vcodec', 'mjpeg',  # Convert video stream to motion jpeg
        'pipe:1'
    ]

    # FFmpeg can now take input directly from the memory buffer and output to a pipe
    frame_data = subprocess.run(
        command,
        input=buffer.getvalue(),  # Use the buffer content as input
        stdout=subprocess.PIPE
    ).stdout

    # Close stream file descriptor and the buffer
    stream_reader.close()
    buffer.close()

    return frame_data

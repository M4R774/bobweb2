import asyncio
import logging
import os
import re
import subprocess
from datetime import datetime
from typing import Dict
from typing import Optional, Tuple

import pytz
import streamlink
from aiohttp import ClientResponseError
from django.utils import html
from streamlink.plugins.twitch import TwitchHLSStream, TwitchHLSStreamReader

from bobweb.bob import config, utils_common, async_http
from bobweb.bob.config import twitch_api_access_token_env_var_name
from bobweb.bob.utils_common import MessageBuilder

logger = logging.getLogger(__name__)

# Pattern that matches Twitch channel link. 'https' and 'www' are optional, so 'twitch.tv/1234' is matched
twitch_channel_link_url_regex_pattern = r'(?:^|\s)(?:https?://)?(?:www\.)?twitch\.tv/([a-zA-Z0-9_]{4,25})'
streamlink_stream_type_best = 'best'


class StreamStatus:
    def __init__(self,
                 user_login: str,
                 stream_is_live: bool,
                 user_name: str = None,
                 game_name: str = None,
                 stream_title: str = None,
                 viewer_count: int = None,
                 started_at: datetime = None,
                 # Thumbnail_url is used for initial stream status update
                 thumbnail_url: str = None):
        self.updated_at = datetime.now(tz=pytz.utc)  # UTC
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
        # UTC, not exact as twitch does not provide this. But if stream status is updated once a minute, should only
        # be one minute off at most
        self.ended_at_utc = None
        # After base url image width and heigh is given
        # For example: 'https://static-cdn.jtvnw.net/previews-ttv/live_user_{channel_name}-{width}x{height}.jpg'
        # Used for getting the initial stream status message quickly
        self.thumbnail_url = thumbnail_url
        # StreamLink videoStream object
        self.streamlink_stream: Optional[TwitchHLSStream] = None

    def update_from(self, other: 'StreamStatus'):
        """ Update stream status with details from another stream status """
        self.updated_at = datetime.now(tz=pytz.utc)  # UTC

        self.stream_is_live = other.stream_is_live
        self.stream_title = other.stream_title
        self.game_name = other.game_name
        self.viewer_count = other.viewer_count

    def to_message_with_html_parse_mode(self):
        # All text received from twitch have to be html escaped
        started_at_fi_tz = utils_common.fitz_from(self.started_at_utc)
        started_today = self.started_at_utc.date() == datetime.today().date()

        if self.stream_is_live:
            if started_today:
                # example: "klo 12:13"
                started_at_localized_str = f'klo {started_at_fi_tz.strftime("%H:%M")}'
            else:
                # example: "1.2.2024 klo 12:13"
                started_at_localized_str = (f'{date_short_str(self.started_at_utc)} '
                                            f'klo {started_at_fi_tz.strftime("%H:%M")}')
            heading_row = f'🔴 {html.escape(self.user_name)} on LIVE! 🔴'
            schedule_row = f'🕒 Striimi alkanut: {started_at_localized_str}'
            viewer_count = f'👀 Katsojia: {self.viewer_count}'
            channel_link_row = f'Katso livenä! www.twitch.tv/{self.user_login}'
        else:
            ended_at_fi_tz = utils_common.fitz_from(self.ended_at_utc)
            started_and_ended_same_day = self.started_at_utc.date() == self.ended_at_utc.date()
            if started_and_ended_same_day:
                # example: "klo 12:13 - 23:45"
                streamed_at = f'klo {started_at_fi_tz.strftime("%H:%M")} - {ended_at_fi_tz.strftime("%H:%M")}'
            else:
                # example: "1.2.2024 klo 12:13 - 2.2.2024 klo 23:45"
                streamed_at = (f'{date_short_str(started_at_fi_tz)} klo {started_at_fi_tz.strftime("%H:%M")} - '
                               f'{date_short_str(ended_at_fi_tz)} klo {ended_at_fi_tz.strftime("%H:%M")}')
            heading_row = f'Kanavan {html.escape(self.user_name)} striimi on päättynyt 🏁'
            schedule_row = f'🕒 Striimattu: {streamed_at}'
            viewer_count = None
            channel_link_row = f'Kanava: www.twitch.tv/{self.user_login}'

        builder = (MessageBuilder(f'<b>{heading_row}</b>')
                   .append_to_new_line(html.escape(self.stream_title), '<i>', '</i>')
                   .append_raw('\n')  # Always empty line after header and description
                   .append_to_new_line(html.escape(self.game_name), '🎮 Peli: ')
                   .append_to_new_line(viewer_count)
                   .append_to_new_line(schedule_row)
                   .append_raw('\n')  # Always empty line before link
                   .append_to_new_line(channel_link_row))
        return builder.message


def date_short_str(date_from: datetime) -> str:
    return f'{date_from.day}.{date_from.month}.{date_from.year}'


class TwitchService:
    """
    Twitch service integrations.
    """

    def __init__(self, access_token: str = None):
        self.access_token: Optional[str] = access_token
        self.streamlink_client: streamlink.Streamlink = streamlink.Streamlink()


# Singleton instance
instance = TwitchService()


async def start_service():
    # Check if current access token is valid
    instance.access_token = await validate_access_token_request_new_if_required()

    # Start hourly token validation cycle as per Twitch requirements. From the documentation:
    # "Any third-party app that calls the Twitch APIs and maintains an OAuth session must call the /validate
    # endpoint to verify that the access token is still valid. This includes web apps, mobile apps, desktop apps,
    # extensions, and chatbots. Your app must validate the OAuth token when it starts and on an hourly basis
    # thereafter."
    # Source: https://dev.twitch.tv/docs/authentication/validate-tokens/
    while instance.access_token is not None:
        # Sleep for an hour and then validate the token
        await asyncio.sleep(60 * 60)
        await validate_access_token_request_new_if_required(instance.access_token)


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
                logger.info(msg='Got new Twitch Client Api access token')
                os.environ[twitch_api_access_token_env_var_name] = current_access_token
        except ClientResponseError as e:
            logger.error(msg='Failed to get new Twitch Client Api access token. Twitch integration is now disabled',
                         exc_info=e)
            return None

    return current_access_token


async def _get_new_access_token() -> Optional[str]:
    """
    Fetches new access token from Twitch. If client api id and / or secret are missing, returns None and logs error
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
    if access_token is None or access_token == '':
        return False
    # https://dev.twitch.tv/docs/authentication/validate-tokens/
    url = 'https://id.twitch.tv/oauth2/validate'
    headers = {'Authorization': f'OAuth {access_token}'}
    response = await async_http.get(url, headers=headers)
    return response.ok


def extract_twitch_channel_url(text: str) -> Optional[str]:
    # Regular expression pattern to match Twitch channel links
    match = re.search(twitch_channel_link_url_regex_pattern, text)
    return match.group(1) if match else None


# Step 3: Make API request to get stream info
async def fetch_stream_status(channel_name: str, try_count: int = 1) -> Optional[StreamStatus]:
    """
    Gets stream status for given channel. Raises exception, if twitch api access token has been invalidated or request
    fails for other reason. If request fails with status code 401, access token is tried to be refreshed.
    :param channel_name:
    :param try_count: number of times the request has been tried
    :return: returns stream status if request to twitch was successful. If request fails or bot has not received valid
             access token returns None
    """

    async def refresh_token_and_retry():
        logger.info('Twitch access token has been invalidated, trying to refresh it')
        instance.access_token = await validate_access_token_request_new_if_required()

        if instance.access_token is None:
            return None
        return await fetch_stream_status(channel_name, try_count + 1)

    if instance.access_token is None:
        return await refresh_token_and_retry()

    # https://dev.twitch.tv/docs/api/reference/#get-streams
    url = f'https://api.twitch.tv/helix/streams'
    headers = {
        'Client-Id': config.twitch_client_api_id,
        'Authorization': f'Bearer {instance.access_token}'
    }
    params = {'user_login': channel_name}

    try:
        response_dict = await async_http.get_json(url, headers=headers, params=params)
    except ClientResponseError as e:
        logger.error(f'Failed to get stream status for {channel_name}. Request returned with response code {e.status}')
        # Try again at most 3 times in case of error.
        if try_count > 3:
            raise e  # Raise original exception
        # Try to renew the token and then try to get stream info again once! If service restart fails,
        # no access token is set and the recall will raise error at the first check
        if e.status == 401:
            return await refresh_token_and_retry()
        raise e

    stream_list = response_dict['data']
    if not stream_list:
        return StreamStatus(user_login=channel_name, stream_is_live=False)

    return parse_stream_status_from_stream_response(stream_list[0])


async def fetch_and_update_stream_status(stream_status: StreamStatus):
    """ Updates given stream status object with new values """
    new_status = await fetch_stream_status(stream_status.user_login)
    if new_status is not None and new_status.stream_is_live:
        stream_status.update_from(new_status)
    else:
        # Stream status fetch has failed or some other error
        stream_status.stream_is_live = False
        stream_status.ended_at_utc = datetime.now(tz=pytz.UTC)


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
    # Initiate Stream link stream object and save to the status object
    if stream_status.streamlink_stream is None:
        twitch_url = "https://www.twitch.tv/" + stream_status.user_login
        available_streams: Dict[TwitchHLSStream] = instance.streamlink_client.streams(twitch_url)
        stream: TwitchHLSStream = available_streams[streamlink_stream_type_best]
        stream.disable_ads = True
        stream_status.streamlink_stream = stream  # Set stream to the stream status object

    # Read enough bytes to ensure getting a full key frame. This value could be adjusted
    # based on the stream's bitrate. However, 256 kt should be sufficient.
    stream_reader: TwitchHLSStreamReader = stream_status.streamlink_stream.open()
    stream_bytes = stream_reader.read(1024 * 512)
    return convert_image_from_video(stream_bytes)


def convert_image_from_video(video_bytes: bytes) -> bytes:
    """
    Converts given video bytes to image bytes using FFMPEG. Throws CalledProcessError if conversion fails or if
    FFMPEG is not installed.
    :param video_bytes:
    :return:
    """
    # ffmpeg command parameters
    command = [
        'ffmpeg',
        '-hide_banner',  # No banner on every call
        '-loglevel', 'error',  # Only error level logging
        '-i', 'pipe:0',  # Use stdin for input
        '-frames:v', '1',  # Get only one frame
        '-f', 'image2pipe',  # Output to a pipe
        '-vcodec', 'mjpeg',  # Convert video stream to motion jpeg
        'pipe:1'
    ]

    # Fmpeg can now take input directly from the memory buffer and output to a pipe
    process = subprocess.run(
        command,
        input=video_bytes,  # Use the buffer content as input
        stdout=subprocess.PIPE
    )
    # Check return code, raise error if it's not 0
    process.check_returncode()
    # Return bytes from the standard output
    return process.stdout

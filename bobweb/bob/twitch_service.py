import asyncio
import logging
import os
import re
from datetime import datetime
from typing import Optional, Tuple

import requests
from aiohttp import ClientResponseError
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import CallbackContext

from bobweb.bob import config, utils_common, async_http
from bobweb.bob.command import ChatCommand, regex_simple_command_with_parameters
from bobweb.bob.config import twitch_client_access_token_env_var_name
from bobweb.bob.resources.bob_constants import FINNISH_DATE_TIME_FORMAT
from bobweb.bob.utils_common import MessageBuilder

logger = logging.getLogger(__name__)


class TwitchCommand(ChatCommand):
    def __init__(self):
        super().__init__(
            name='twitch',
            regex=regex_simple_command_with_parameters('twitch'),
            help_text_short=('/twitch', 'Antaa striimin tilan')
        )

    async def handle_update(self, update: Update, context: CallbackContext = None):
        if not update.effective_message.text:
            await update.effective_chat.send_message(
                'Annan kanavan nimi tai url parametrina saadaksesi tieto sen tilasta')
        contains_channel_link, channel_name = contains_twitch_channel_link(update.effective_message.text)
        if not contains_channel_link:
            channel_name = self.get_parameters(update.effective_message.text)

        status = get_stream_status(channel_name)
        if not status.stream_is_live:
            await update.effective_chat.send_message('Stream ei ole live')
            return

        started_at_fi_tz = utils_common.fitz_from(status.started_at_utc)
        started_at_localized_str = started_at_fi_tz.strftime(FINNISH_DATE_TIME_FORMAT) if status.started_at_utc else ''

        reply = (MessageBuilder(f'<b>🔴 {status.channel_name} on LIVE! 🔴</b>')
                 .append_to_new_line(status.stream_title, '<i>', '</i>')
                 .append_raw('\n')  # Always empty line after header and description
                 .append_to_new_line(status.game_name, '🎮 Peli: ')
                 .append_to_new_line(status.viewer_count, '👀 Katsojia: ')
                 .append_to_new_line(started_at_localized_str, '🕒 Striimi alkanut: ')
                 .append_raw('\n')  # Always empty line before link
                 .append_to_new_line(f'Katso livenä! <a href="www.twitch.tv/{channel_name}">twitch.tv/{channel_name}</a>')
                 ).message

        # 1280x720 thumbnail image should be sufficient
        thumbnail_url = status.thumbnail_url.replace('{width}', '1280').replace('{height}', '720')

        try:
            fetched_bytes: Optional[bytes] = await async_http.fetch_content_bytes(thumbnail_url)
        except ClientResponseError as e:
            fetched_bytes = None
            logger.error(msg='Error while trying to fetch twitch stream thumbnail', exc_info=e)

        if fetched_bytes:
            await update.effective_chat.send_photo(photo=fetched_bytes, caption=reply, parse_mode=ParseMode.HTML)
        else:
            await update.effective_chat.send_message(text=reply, parse_mode=ParseMode.HTML)


class StreamStatus:
    def __init__(self,
                 channel_name: str,
                 stream_is_live: bool,
                 game_name: str = None,
                 stream_title: str = None,
                 viewer_count: int = None,
                 started_at_utc: datetime = None,
                 thumbnail_url: str = None):
        self.channel_name = channel_name
        self.stream_is_live = stream_is_live
        self.game_name = game_name
        self.stream_title = stream_title
        self.viewer_count = viewer_count
        self.started_at_utc = started_at_utc
        # After base url image width and heigh is given
        # For example: 'https://static-cdn.jtvnw.net/previews-ttv/live_user_{channel_name}-{width}x{height}.jpg'
        self.thumbnail_url = thumbnail_url


class TwitchService:
    """
    Class for Twitch service integrations.
    """
    def __init__(self):
        self.access_token: Optional[str] = None

    async def start_service(self):
        # Check if current access token is valid
        self.access_token: Optional[str] = validate_access_token_request_new_if_required()

        # Start hourly token validation cycle as per Twitch requirements. From the documentation:
        # "Any third-party app that calls the Twitch APIs and maintains an OAuth session must call the /validate
        # endpoint to verify that the access token is still valid. This includes web apps, mobile apps, desktop apps,
        # extensions, and chatbots. Your app must validate the OAuth token when it starts and on an hourly basis
        # thereafter."
        # Source: https://dev.twitch.tv/docs/authentication/validate-tokens/
        while True:
            # Sleep for an hour and then validate the token
            await asyncio.sleep(60 * 60)
            validate_access_token_request_new_if_required(self.access_token)


# Singleton instance
instance = TwitchService()


def validate_access_token_request_new_if_required(current_access_token: str = None) -> Optional[str]:
    """
    Validates current access token or requires new if current has been invalidated
    :param current_access_token: if empy, current token is fetched from env variables
    :return: new token or None if token request failed or new token was rejected
    """
    if current_access_token is None:
        current_access_token = os.getenv(twitch_client_access_token_env_var_name)

    token_ok = _is_access_token_valid(current_access_token)
    if not token_ok:
        try:
            # Replace current access token with a new one
            current_access_token = _get_new_access_token()
            # Update access token to env variables
            os.environ[twitch_client_access_token_env_var_name] = current_access_token
        except Exception as e:
            logger.error(msg='Failed to get new Twitch Client Api access token. Twitch integration is now disabled',
                         exc_info=e)
            return None

    return current_access_token


def _get_new_access_token() -> str:
    url = 'https://id.twitch.tv/oauth2/token'
    params = {
        'client_id': config.twitch_client_api_id,
        'client_secret': config.twitch_client_api_secret,
        'grant_type': 'client_credentials'
    }
    response = requests.post(url, params=params)
    data = response.json()
    return data.get('access_token')


def _is_access_token_valid(access_token: str) -> bool:
    url = 'https://id.twitch.tv/oauth2/validate'
    headers = {'Authorization': f'OAuth {access_token}'}
    response = requests.get(url, headers=headers)
    return response.ok


def contains_twitch_channel_link(text: str) -> Tuple[bool, Optional[str]]:
    # Regular expression pattern to match Twitch channel links
    pattern = r'(?:https?://)?(?:www\.)?twitch\.tv/([a-zA-Z0-9_]{4,25})'
    match = re.search(pattern, text)
    if match:
        return True, match.group(1)
    else:
        return False, None


# Step 3: Make API request to get stream info
def get_stream_status(channel_name: str) -> StreamStatus:
    url = f'https://api.twitch.tv/helix/streams'
    headers = {
        'Client-Id': config.twitch_client_api_id,
        'Authorization': f'Bearer {instance.access_token}'
    }
    params = {'user_login': channel_name}
    response = requests.get(url, headers=headers, params=params)
    response_dict = response.json()
    stream_list = response_dict['data']

    if not stream_list:
        print(f"{channel_name} is currently offline.")
        return StreamStatus(channel_name=channel_name, stream_is_live=False)

    logger.info(f"{channel_name} is currently live!")
    logger.info(stream_list[0])

    return parse_stream_status_from_stream_response(stream_list[0])


def parse_stream_status_from_stream_response(data: dict) -> StreamStatus:
    started_at_str = data['started_at']
    date_time_format = '%Y-%m-%dT%H:%M:%SZ'
    started_at_dt = utils_common.strptime_or_none(started_at_str, date_time_format)
    return StreamStatus(
        channel_name=data['user_name'],
        stream_is_live=True,
        game_name=data['game_name'],
        stream_title=data['title'],
        viewer_count=data['viewer_count'],
        started_at_utc=started_at_dt,
        thumbnail_url=data['thumbnail_url']
    )

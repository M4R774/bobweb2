import asyncio
import logging
import os
import re
from datetime import datetime
from typing import Optional, Tuple

from aiohttp import ClientResponse, ClientResponseError

from bobweb.bob import config, utils_common, async_http
from bobweb.bob.config import twitch_client_access_token_env_var_name

logger = logging.getLogger(__name__)


# Pattern that matches Twitch channel link. 'https' and 'www' are optional, so twitch.tv/1234 is matched
twitch_channel_link_url_regex_pattern = r'(?:https?://)?(?:www\.)?twitch\.tv/([a-zA-Z0-9_]{4,25})'


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


class TwitchServiceAuthError(Exception):
    """ Error for when authorization fails with Twitch servers """
    def __init__(self, *args: object) -> None:
        super().__init__(*args)


def raise_auth_error_if_no_access_token():
    if not instance.access_token:
        raise TwitchServiceAuthError('Twitch access token is not valid')


class TwitchService:
    """
    Class for Twitch service integrations.
    """
    def __init__(self, access_token: str = None):
        self.access_token: Optional[str] = access_token

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
        current_access_token = os.getenv(twitch_client_access_token_env_var_name)

    token_ok = await _is_access_token_valid(current_access_token)
    if not token_ok:
        try:
            # Replace current access token with a new one
            current_access_token = await _get_new_access_token()
            if current_access_token is not None:
                # Update access token to env variables
                os.environ[twitch_client_access_token_env_var_name] = current_access_token
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
async def get_stream_status(channel_name: str) -> StreamStatus:
    """
    Gets stream status for given channel. Raises exception, if twitch api access token has been invalidated or request
    fails for other reason. If request fails with status code 401, access token is tried to be refreshed.
    :param channel_name:
    :return:
    """
    raise_auth_error_if_no_access_token()

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
        return StreamStatus(channel_name=channel_name, stream_is_live=False)

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

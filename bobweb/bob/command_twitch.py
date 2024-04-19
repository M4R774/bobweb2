import asyncio
import datetime
import logging
from typing import Optional

import pytz
import streamlink
from aiohttp import ClientResponseError
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import CallbackContext

from bobweb.bob import utils_common, async_http, twitch_service, command_service
from bobweb.bob.activities.activity_state import ActivityState
from bobweb.bob.command import ChatCommand, regex_simple_command_with_parameters

logger = logging.getLogger(__name__)


class TwitchCommand(ChatCommand):
    def __init__(self):
        super().__init__(
            name='twitch',
            # Normal 'twitch'-command or just url to twitch channel
            regex=f'{regex_simple_command_with_parameters("twitch")}'
                  f'|{twitch_service.twitch_channel_link_url_regex_pattern}',
            help_text_short=('/twitch', 'Antaa striimin tilan')
        )

    async def handle_update(self, update: Update, context: CallbackContext = None):
        contains_channel_link, channel_name = twitch_service.extract_twitch_channel_url(update.effective_message.text)
        if not contains_channel_link:
            channel_name = self.get_parameters(update.effective_message.text)

        # No channel url or name provided
        if not channel_name:
            await update.effective_chat.send_message('Anna komennon parametrina kanavan nimi tai linkki kanavalle')
            return

        status = await twitch_service.get_stream_status(channel_name)

        if not status:
            await update.effective_chat.send_message('Yhteyden muodostaminen Twitchin palvelimiin epäonnistui 🔌✂️')
            return

        if not status.stream_is_live:
            await update.effective_chat.send_message('Annettua kanavaa ei löytynyt tai sillä ei ole striimi live')
            return

        await command_service.instance.start_new_activity(update, TwitchStreamUpdatedSteamStatusState(status))


class TwitchStreamUpdatedSteamStatusState(ActivityState):
    """ For creating stream status messages that update itself periodically. """
    # Initial idea was to have update button that user could press to update stream status. However, as Twitch provides
    # new stream thumbnail every 5 or so minutes, manual update would be kind of lackluster with only viewer count
    # being updated. Implementation for manual update commented out, as there might be a way to add more frequent
    # stream thumbnail updates.
    update_status_button = InlineKeyboardButton(text='Päivitä', callback_data='/update_status')
    update_interval_in_seconds = 60 * 5  # 5 minutes

    def __init__(self, stream_status: twitch_service.StreamStatus):
        super(TwitchStreamUpdatedSteamStatusState, self).__init__()
        self.stream_status = stream_status
        # When was the stream status last updated
        self.last_stream_status_update = datetime.datetime.now(tz=pytz.utc)
        # Next scheduled stream status update task
        self.update_task: Optional[asyncio.Task] = None
        # How many times has users request for update been rejected
        # self.rejected_update_count = 0

    async def execute_state(self, **kwargs):
        # Reply with the initial state
        await self.create_and_send_message_update(self.stream_status, first_update=True)

        # Start updating the state every 5 minutes
        self.update_task = asyncio.create_task(self.wait_and_update_task())
        await self.update_task

    async def wait_and_update_task(self):
        # Sleep for 5 minutes and then update stream status
        await asyncio.sleep(TwitchStreamUpdatedSteamStatusState.update_interval_in_seconds)
        await self.update_stream_status()

    async def update_stream_status(self):
        status = await twitch_service.get_stream_status(self.stream_status.channel_name)
        # stream status is overridden only if still live.
        # When stream goes offline, only it's online status is updated.
        if status and status.stream_is_live:
            await self.create_and_send_message_update(status)
            self.stream_status = status

            # Create new update task if stream is still live
            self.update_task = asyncio.create_task(self.wait_and_update_task())
            await self.update_task
        else:
            self.update_task.done()  # Not sure if needed. Just to be sure
            self.update_task = None
            self.stream_status.stream_is_live = False
            await self.create_and_send_message_update(self.stream_status)

    async def create_and_send_message_update(self, stream_status: twitch_service.StreamStatus,
                                             first_update: bool = False):
        last_update_time = utils_common.fitz_from(stream_status.created_at).strftime("%H:%M:%S")
        message_text = stream_status.to_message_with_html_parse_mode()

        if stream_status.stream_is_live:
            message_text += f'\n(Viimeisin päivitys klo {last_update_time})'

        # If this is the first time the stream status has been updated, send the thumbnail image
        # (faster, but is updated only every 5 minutes). On sequential updates, fetch fresh image from the stream
        # and use that (is slower, but is always up to date)
        if first_update:
            image_bytes = await get_twitch_provided_thumbnail_image(stream_status)
        else:
            # On sequential updates, use fresh image from the stream as primary source and Twitch API provided
            # thumbnail as seconday source
            image_bytes: Optional[bytes] = (capture_single_frame_from_stream(stream_status)
                                            or await get_twitch_provided_thumbnail_image(stream_status))

        keyboard = InlineKeyboardMarkup([[TwitchStreamUpdatedSteamStatusState.update_status_button]])
        await self.activity.reply_or_update_host_message(
            message_text, markup=keyboard, parse_mode=ParseMode.HTML, photo=image_bytes)

    async def handle_response(self, response_data: str, context: CallbackContext = None):
        # Handling user button presses that should update stream status
        if response_data == self.update_status_button.callback_data:
            # Cancel current update task (if any)
            if self.update_task:
                self.update_task.cancel()
            await self.update_stream_status()


async def get_twitch_provided_thumbnail_image(stream_status: twitch_service.StreamStatus) -> Optional[bytes]:
    # 1280x720 thumbnail image should be sufficient
    thumbnail_url = (stream_status.thumbnail_url
                     .replace('{width}', '1280')
                     .replace('{height}', '720'))
    try:
        return await async_http.get_content_bytes(thumbnail_url)
    except ClientResponseError as e:
        logger.error(msg='Error while trying to fetch twitch stream thumbnail', exc_info=e)
        return None


def capture_single_frame_from_stream(stream_status: twitch_service.StreamStatus) -> Optional[bytes]:
    try:
        return twitch_service.capture_frame("https://www.twitch.tv/" + stream_status.channel_name)
    except Exception:
        return None

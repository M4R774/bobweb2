import asyncio
import logging
from typing import Optional

import telegram
from aiohttp import ClientResponseError
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Message, InputMediaPhoto
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

        stream_status = await twitch_service.get_stream_status(channel_name)

        if not stream_status:
            await update.effective_chat.send_message('Yhteyden muodostaminen Twitchin palvelimiin epäonnistui 🔌✂️')
            return

        if not stream_status.stream_is_live:
            await update.effective_chat.send_message('Annettua kanavaa ei löytynyt tai sillä ei ole striimi live')
            return

        new_activity_state = TwitchStreamUpdatedSteamStatusState(stream_status)
        await command_service.instance.start_new_activity(update, new_activity_state)


class TwitchStreamUpdatedSteamStatusState(ActivityState):
    """ For creating stream status messages that update itself periodically. """
    update_status_button = InlineKeyboardButton(text='Päivitä', callback_data='/update_status')
    update_interval_in_seconds = 60  # 1 minute

    def __init__(self, stream_status: twitch_service.StreamStatus):
        super(TwitchStreamUpdatedSteamStatusState, self).__init__()
        self.stream_status: twitch_service.StreamStatus = stream_status
        # Next scheduled stream status update task
        self.update_task: Optional[asyncio.Task] = None

    async def execute_state(self, **kwargs):
        """ Execute state is called only once when the activity is started. """
        # Reply with the initial state
        await self.create_and_send_message_update(first_update=True)

        # Start updating the state every 5 minutes
        self.update_task = asyncio.create_task(self.wait_and_update_task())
        await self.update_task

    async def wait_and_update_task(self):
        await asyncio.sleep(TwitchStreamUpdatedSteamStatusState.update_interval_in_seconds)
        await self.update_stream_status_message()

    async def update_stream_status_message(self):
        if self.update_task is not None:
            self.update_task.done()
            self.update_task = None

        # Update current stream status and send message update
        await twitch_service.update_stream_status(self.stream_status)
        await self.create_and_send_message_update()

        # When stream goes offline, only it's online status is updated.
        if self.stream_status.stream_is_live:
            # Create new update task if stream is still live. Update message and then start new update timer
            self.update_task = asyncio.create_task(self.wait_and_update_task())
            await self.update_task
        else:
            # If stream is offline, mark current chat activity as done
            await self.activity.done()

    async def create_and_send_message_update(self, first_update: bool = False):
        """
        Creates and sends stream status message with image. Stream image frame and its status are send in separate
        messages. Updates self.stream_image_message
        :param first_update:
        :return:
        """
        last_update_time = utils_common.fitz_from(self.stream_status.updated_at).strftime("%H:%M:%S")
        message_text = self.stream_status.to_message_with_html_parse_mode()

        if self.stream_status.stream_is_live:
            message_text += f'\n(Viimeisin päivitys klo {last_update_time})'

        # If this is the first time the stream status has been updated, send the image
        # (faster, but is updated only every 5 minutes). On sequential updates, fetch fresh image from the stream
        # and use that (is slower, but is always up-to-date)
        if first_update:
            image_bytes: bytes = await get_twitch_provided_thumbnail_image(self.stream_status)
        else:
            # On sequential updates, use fresh image from the stream as primary source and Twitch API provided
            # thumbnail as secondary source
            image_bytes: Optional[bytes] = capture_single_frame_from_stream(self.stream_status)
            if not image_bytes:
                # If creating image from live stream fails for some reason and twitch offered thumbnail image is used
                image_bytes: bytes = await get_twitch_provided_thumbnail_image(self.stream_status)

        keyboard = InlineKeyboardMarkup([[TwitchStreamUpdatedSteamStatusState.update_status_button]])
        await self.send_or_update_host_message(message_text,
                                               photo=image_bytes,
                                               markup=keyboard,
                                               parse_mode=ParseMode.HTML,
                                               disable_web_page_preview=True)

    async def handle_response(self, response_data: str, context: CallbackContext = None):
        # Handling user button presses that should update stream status
        if response_data == self.update_status_button.callback_data:
            # Cancel current update task (if any)
            # if self.update_task:
            #     self.update_task.done()
            await self.update_stream_status_message()


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
        return twitch_service.capture_frame(stream_status)
    except Exception as e:
        logger.error(msg='Twtich stream frame update failed', exc_info=e)
        return None

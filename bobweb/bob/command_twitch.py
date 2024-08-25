import asyncio
import logging
from typing import Optional

import telegram
from aiohttp import ClientResponseError
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Message, InputMediaPhoto
from telegram.constants import ParseMode
from telegram.ext import CallbackContext

from bobweb.bob import utils_common, async_http, twitch_service, command_service, message_board_service
from bobweb.bob.activities.activity_state import ActivityState
from bobweb.bob.activities.command_activity import CommandActivity
from bobweb.bob.command import ChatCommand, regex_simple_command_with_parameters
from bobweb.bob.message_board import EventMessage
from bobweb.bob.utils_common import handle_exception_async

logger = logging.getLogger(__name__)


class TwitchCommand(ChatCommand):
    def __init__(self):
        super().__init__(
            name='twitch',
            # Normal 'twitch'-command or just url to twitch channel
            regex=f'{regex_simple_command_with_parameters("twitch")}',
            help_text_short=('/twitch [kanava]', 'Antaa striimin tilan')
        )

    async def handle_update(self, update: Update, context: CallbackContext = None):
        channel_name = twitch_service.extract_twitch_channel_url(update.effective_message.text)
        if not channel_name:
            channel_name = self.get_parameters(update.effective_message.text)

        # No channel url or name provided
        if not channel_name:
            await update.effective_chat.send_message('Anna komennon parametrina kanavan nimi tai linkki kanavalle')
            return

        try:
            stream_status = await twitch_service.fetch_stream_status(channel_name)
        except ClientResponseError as e:
            logger.error(f'Failed to get stream status for {channel_name}. '
                         f'Request returned with response code {e.status}')
            await update.effective_chat.send_message('Yhteyden muodostaminen Twitchin palvelimiin epäonnistui 🔌✂️')
            return

        if stream_status is None:
            await update.effective_chat.send_message('Annetun nimistä Twitch kanavaa ei ole olemassa')
            return

        if not stream_status.stream_is_live:
            await update.effective_chat.send_message('Kanava ei striimaa nyt mitään')
            return

        # If there is a stream active, start new Activity with state that updates itself
        new_activity_state = TwitchStreamUpdatedSteamStatusState(stream_status)

        # If the chat has message board active, add event message to the board
        event_message = await create_event_message_to_notification_board(update.effective_message.chat_id,
                                                                         update.effective_message.message_id,
                                                                         new_activity_state)
        new_activity_state.message_board_event_message = event_message

        await command_service.instance.start_new_activity(update, new_activity_state)


class TwitchStreamUpdatedSteamStatusState(ActivityState):
    """ For creating stream status messages that update itself periodically. """
    update_interval_in_seconds = 60  # 1 minute

    def __init__(self, stream_status: twitch_service.StreamStatus):
        super(TwitchStreamUpdatedSteamStatusState, self).__init__()
        self.stream_status: twitch_service.StreamStatus = stream_status
        # Message board event message if this activity's chat is using message board
        self.message_board_event_message: EventMessage | None = None
        # Next scheduled stream status update task
        self.update_task: Optional[asyncio.Task] = None

    async def execute_state(self, **kwargs):
        """ Execute state is called only once when the activity is started. """
        # Reply with the initial state
        await self.create_and_send_message_update(first_update=True)

        # Start updating the state every minute
        while self.stream_status.stream_is_live:
            # Create new update task if stream is still live. Update message and then start new update timer
            await self.wait_and_update_task()

        logger.info("Stream has gone offline")
        await self.activity.done()

        # await self.update_task

    async def wait_and_update_task(self):
        try:
            await asyncio.sleep(TwitchStreamUpdatedSteamStatusState.update_interval_in_seconds)
            # Update current stream status and send message update
            await twitch_service.fetch_and_update_stream_status(self.stream_status)
            logger.info("Stream status updated for stream " + self.stream_status.user_name + ". Is live: " + str(self.stream_status.stream_is_live))
            await self.create_and_send_message_update()
        except asyncio.CancelledError:
            pass  # Do nothing

    async def create_and_send_message_update(self, first_update: bool = False):
        """
        Creates and sends stream status message with image.
        :param first_update:
        :return:
        """
        last_update_time = utils_common.fitz_from(self.stream_status.updated_at).strftime("%H:%M:%S")
        message_text = self.stream_status.to_message_with_html_parse_mode()

        # New image is fetched and updated only if the stream is live. Otherwise, only the caption of the current
        # image is updated.
        image_bytes: Optional[bytes] = None
        if self.stream_status.stream_is_live:
            message_text += f'\n(Viimeisin päivitys klo {last_update_time})'

            if self.message_board_event_message:
                # If there is message board message active, update its content. Does not trigger message board update,
                # so new content will be updated to the board on it's next update.
                self.message_board_event_message.message = message_text

            image_bytes = await fetch_stream_frame(stream_status=self.stream_status, first_update=first_update)

        elif self.message_board_event_message is not None:
            # When stream goes offline, if message board is active in the chat, update the stream status message in the
            # message board.
            # Update message board message content.
            self.message_board_event_message.message = message_text
            await self.message_board_event_message.remove_this_message_from_board()

        await self.send_or_update_host_message(text=message_text,
                                               photo=image_bytes,
                                               parse_mode=ParseMode.HTML,
                                               disable_web_page_preview=True)


async def fetch_stream_frame(stream_status: twitch_service.StreamStatus, first_update: bool = False) -> bytes | None:
    # If this is the first time the stream status has been updated, send the image
    # (faster, but is updated only every 5 minutes). On sequential updates, fetch fresh image from the stream
    # and use that (is slower, but is always up-to-date)
    if first_update:
        return await get_twitch_provided_thumbnail_image(stream_status)
    else:
        # On sequential updates, use fresh image from the stream as primary source and Twitch API provided
        # thumbnail as secondary source
        image_bytes = await capture_single_frame_from_stream(stream_status)
        if not image_bytes:
            # If creating image from live stream fails for some reason, twitch offered thumbnail image is used
            image_bytes = await get_twitch_provided_thumbnail_image(stream_status)
        return image_bytes


async def create_event_message_to_notification_board(chat_id: int,
                                                     message_id: int,
                                                     activity_state: TwitchStreamUpdatedSteamStatusState) -> EventMessage | None:
    """ If chat is using notification boards, adds a new Twitch Stream event to the board """
    board = message_board_service.instance.find_board(chat_id)
    if board is None:
        return  # Chat has no message board -> No further action
    message_text = activity_state.stream_status.to_message_with_html_parse_mode()
    event_message = EventMessage(message_text, None, message_id, ParseMode.HTML)

    await board.add_event_message(event_message)
    return event_message


@handle_exception_async(exception_type=ClientResponseError,
                        log_msg='Error while trying to fetch twitch stream thumbnail')
async def get_twitch_provided_thumbnail_image(stream_status: twitch_service.StreamStatus) -> Optional[bytes]:
    # 1280x720 thumbnail image should be sufficient
    thumbnail_url = (stream_status.thumbnail_url
                     .replace('{width}', '1280')
                     .replace('{height}', '720'))
    return await async_http.get_content_bytes(thumbnail_url)


@handle_exception_async(exception_type=Exception, log_msg='Twitch stream frame update failed')
async def capture_single_frame_from_stream(stream_status: twitch_service.StreamStatus) -> Optional[bytes]:
    """ Captures a single frame from the live stream.
        Note! Implementation is synchronous and takes multiple seconds. """
    return await twitch_service.capture_frame(stream_status)

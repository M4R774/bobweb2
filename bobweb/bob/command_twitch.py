import logging
from typing import Optional

from aiohttp import ClientResponseError
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import CallbackContext

from bobweb.bob import utils_common, async_http, twitch_service
from bobweb.bob.command import ChatCommand, regex_simple_command_with_parameters
from bobweb.bob.resources.bob_constants import FINNISH_DATE_TIME_FORMAT
from bobweb.bob.utils_common import MessageBuilder

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

        try:
            status = await twitch_service.get_stream_status(channel_name)
        except twitch_service.TwitchServiceAuthError as e:
            logger.error("Twitch stream status check failed.", exc_info=e)
            await update.effective_chat.send_message('Yhteyden muodostaminen Twitchin palvelimiin epäonnistui 🔌✂️')
            return

        if not status.stream_is_live:
            await update.effective_chat.send_message('Annettua kanavaa ei löytynyt tai sillä ei ole striimi live')
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
            fetched_bytes: Optional[bytes] = await async_http.get_content_bytes(thumbnail_url)
        except ClientResponseError as e:
            fetched_bytes = None
            logger.error(msg='Error while trying to fetch twitch stream thumbnail', exc_info=e)

        if fetched_bytes:
            await update.effective_chat.send_photo(photo=fetched_bytes, caption=reply, parse_mode=ParseMode.HTML)
        else:
            await update.effective_chat.send_message(text=reply, parse_mode=ParseMode.HTML)

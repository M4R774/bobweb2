import logging
from typing import List

import telegram
from telegram import Bot
from telegram.constants import ParseMode

from bobweb.bob import database
from bobweb.web.bobapp.models import Chat

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)  #NOSONAR
logger = logging.getLogger(__name__)


async def broadcast(bot: Bot, text: str):
    """ Broadcasts fo all chats known to bot that have broadcast enabled """
    chats = [chat for chat in database.get_chats() if chat.broadcast_enabled]
    await broadcast_to_chats(bot, chats, text)


async def broadcast_to_chats(bot: Bot,
                             chats: List[Chat],
                             text: str,
                             image_bytes: bytes = None,
                             parse_mode: ParseMode = None):
    """ Broadcasts given message to all given chats. Sends image if given as parameter """
    if text is not None and text != "":
        for chat in chats:
            try:
                if image_bytes is not None:
                    await bot.send_photo(chat_id=chat.id, photo=image_bytes, caption=text, parse_mode=parse_mode)
                else:
                    await bot.send_message(chat_id=chat.id, text=text, parse_mode=parse_mode)
            except telegram.error.BadRequest as e:
                logger.error("Tried to broadcast to chat with id " + str(chat.id) +
                             " but Telegram-API responded with \"BadRequest: " + str(e) + "\"")
            except telegram.error.Forbidden as e2:
                logger.error("Tried to broadcast to chat with id " + str(chat.id) +
                             " but Telegram-API responded with \"BadRequest: " + str(e2) + "\""
                             "User has propably blocked bot so broadcast is disabled in the chat.")
                chat.broadcast_enabled = False
                chat.save()


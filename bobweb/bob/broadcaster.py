import logging
from typing import List

import telegram
from telegram import Bot
from telegram.constants import ParseMode

from bobweb.bob import database
from bobweb.web.bobapp.models import Chat, TelegramUser

logger = logging.getLogger(__name__)


async def broadcast(bot: Bot, text: str, parse_mode: ParseMode = None):
    """ Broadcasts fo all chats known to bot that have broadcast enabled """
    chats: List[int] = [chat.id for chat in database.get_chats() if chat.broadcast_enabled]
    await broadcast_to_chats(bot, chats, text, parse_mode=parse_mode)


async def broadcast_to_chats(bot: Bot,
                             chat_ids: List[int],
                             text: str,
                             image_bytes: bytes = None,
                             parse_mode: ParseMode = None):
    """ Broadcasts given message to all given chats. Sends image if given as parameter """
    if text is not None and text != "":
        for chat_id in chat_ids:
            try:
                if image_bytes is not None:
                    await bot.send_photo(chat_id=chat_id, photo=image_bytes, caption=text, parse_mode=parse_mode)
                else:
                    await bot.send_message(chat_id=chat_id, text=text, parse_mode=parse_mode)
            except telegram.error.BadRequest as e:
                logger.error(f"Tried to broadcast to chat with id {chat_id}" +
                             " but Telegram-API responded with \"BadRequest: " + str(e) + "\"")
            except telegram.error.Forbidden as e:
                logger.error(f"Tried to broadcast to chat with id {chat_id}" +
                             " but Telegram-API responded with \"BadRequest: " + str(e) + "\""
                             "User has propably blocked bot so broadcast is disabled in the chat.")
                chat = database.get_chat(chat_id=chat_id)
                chat.broadcast_enabled = False
                chat.save()


async def send_file_to_global_admin(file, bot):
    global_admin_tg_user: TelegramUser = database.get_global_admin()
    if global_admin_tg_user is not None:
        # Private chat id is the same as the users id
        await bot.send_document(global_admin_tg_user.id, file)
    else:
        await broadcast(bot, "Varmuuskopiointi pilveen epäonnistui, global_admin ei ole asetettu.")

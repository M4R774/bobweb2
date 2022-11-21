import logging

import telegram
from asgiref.sync import sync_to_async

from bobweb.bob import database


logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)  #NOSONAR
logger = logging.getLogger(__name__)


@sync_to_async
def broadcast(bot, message):
    if message is not None and message != "":
        chats = database.get_chats()
        for chat in chats:
            if chat.broadcast_enabled:
                try:
                    bot.sendMessage(chat.id, message)
                except telegram.error.BadRequest as e:
                    logger.error("Tried to broadcast to chat with id " + str(chat.id) +
                                 " but Telegram-API responded with \"BadRequest: " + str(e) + "\"")
                except telegram.error.Unauthorized as e2:
                    logger.error("Tried to broadcast to chat with id " + str(chat.id) +
                                 " but Telegram-API responded with \"BadRequest: " + str(e2) + "\""
                                 "User has propably blocked bot so broadcast is disabled in the chat.")
                    chat.broadcast_enabled = False
                    chat.save()
#!/usr/bin/env python
import logging
import os

import telegram.error
from asgiref.sync import sync_to_async
from telegram import Update
from telegram.ext import Updater, MessageHandler, Filters, CallbackContext

import scheduler
import database
import command_service
from git_promotions import broadcast_and_promote
from message_handler import message_handler

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)

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


@sync_to_async
def send_file_to_global_admin(file, bot):
    if database.get_global_admin() is not None:
        bot.send_document(database.get_global_admin().id, file)
    else:
        broadcast("Varmuuskopiointi pilveen epäonnistui, global_admin ei ole asetettu.")


def init_bot():
    token = os.getenv("BOT_TOKEN")
    if token == "" or token is None:
        logger.critical("BOT_TOKEN env variable is not set. ")
        raise ValueError("BOT_TOKEN env variable is not set. ")
    print(token)

    # Create the Updater and pass it your bot's token.
    updater = Updater(token)

    # Get the dispatcher to register handlers
    dispatcher = updater.dispatcher

    # Initialize broadcast and promote features
    broadcast_and_promote(updater)

    # Initialize all command handlers
    command_service.CommandService()

    # on different commands - answer in Telegram
    dispatcher.add_handler(MessageHandler(Filters.all, message_handler))  # KAIKKI viestit
    # on non command i.e message - echo the message on Telegram
    # dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, echo))

    return updater


def main() -> None:
    updater = init_bot()
    updater.start_polling()  # Start the bot
    scheduler.Scheduler(updater)

    # Run the bot until you press Ctrl-C or the process receives SIGINT,
    # SIGTERM or SIGABRT. This should be used most of the time, since
    # start_polling() is non-blocking and will stop the bot gracefully.
    updater.idle()


if __name__ == '__main__':
    main()

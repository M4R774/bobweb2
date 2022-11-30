#!/usr/bin/env python
import os
import logging

from asgiref.sync import sync_to_async
from telegram.ext import Updater, MessageHandler, Filters, CallbackQueryHandler

from bobweb.bob import scheduler
from bobweb.bob import database
from bobweb.bob import command_service
from bobweb.bob.broadcaster import broadcast
from bobweb.bob.git_promotions import broadcast_and_promote
from bobweb.bob.message_handler import handle_update

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)


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

    # Initialize all command handlers
    command_service_instance = command_service.instance

    # on different commands - answer in Telegram
    # is invoked for EVERY update (message) including replies and message edits
    dispatcher.add_handler(MessageHandler(Filters.all, handle_update, edited_updates=True))

    # callback query is handled by command service
    dispatcher.add_handler(CallbackQueryHandler(command_service_instance.reply_and_callback_query_handler))

    # Initialize broadcast and promote features
    broadcast_and_promote(updater)

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

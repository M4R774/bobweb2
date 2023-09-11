#!/usr/bin/env python
import asyncio
import os
import logging

from asgiref.sync import sync_to_async
from telegram.ext import MessageHandler, CallbackQueryHandler, Application, filters, ContextTypes

from bobweb.bob import scheduler, message_handler_voice, async_http
from bobweb.bob import database
from bobweb.bob import command_service
from bobweb.bob.broadcaster import broadcast
from bobweb.bob.git_promotions import broadcast_and_promote
from bobweb.bob.async_http import HttpClient
from bobweb.bob.message_handler import handle_update

logging_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
logging.basicConfig(format=logging_format, level=logging.DEBUG)  # NOSONAR
logger = logging.getLogger(__name__)


async def send_file_to_global_admin(file, bot):
    if database.get_global_admin() is not None:
        await bot.send_document(database.get_global_admin().id, file)
    else:
        await broadcast(bot, "Varmuuskopiointi pilveen epäonnistui, global_admin ei ole asetettu.")


def init_bot() -> Application:
    token = os.getenv("BOT_TOKEN")
    if token == "" or token is None:
        logger.critical("BOT_TOKEN env variable is not set. ")
        raise ValueError("BOT_TOKEN env variable is not set. ")
    print(token)

    # Create the Application with bot's token.
    application = Application.builder().token(token).build()

    # on different commands - answer in Telegram
    # is invoked for EVERY update (message) including replies and message edits
    application.add_handler(MessageHandler(filters.ALL, handle_update))

    # callback query is handled by command service
    application.add_handler(CallbackQueryHandler(command_service.instance.reply_and_callback_query_handler))

    notify_if_ffmpeg_not_available()

    return application


def notify_if_ffmpeg_not_available():
    if not message_handler_voice.ffmpeg_available:
        warning = 'NOTE! ffmpeg program not available. Command depending on video- and/or ' \
                  'audio conversion won\'t work. To enable, install ffmpeg and make it runnable' \
                  'from the terminal / command prompt.'
        logger.warning(warning)


def main() -> None:
    # Initiate bot application
    application: Application = init_bot()

    # Create new session for internal http_client
    async_http.client.create_session()

    # Add scheduled tasks before starting polling
    scheduler.Scheduler(application)

    logger.info("Starting polling")
    # Start polling. This is blocking method and all after this is run only
    # after the application is stopped
    application.run_polling()

    application.updater.idle()
    logger.info("Application stopped")

    # As a last thing close http_client connection
    asyncio.run(async_http.client.close())


if __name__ == '__main__':
    main()

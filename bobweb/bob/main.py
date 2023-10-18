#!/usr/bin/env python
import asyncio
import os
import logging

from asgiref.sync import sync_to_async
from telegram.ext import MessageHandler, CallbackQueryHandler, Application, filters, ContextTypes
from telethon import TelegramClient

from bobweb.bob import scheduler, message_handler_voice, async_http, telethon_client
from bobweb.bob import database
from bobweb.bob import command_service
from bobweb.bob.broadcaster import broadcast
from bobweb.bob.git_promotions import broadcast_and_promote
from bobweb.bob.async_http import HttpClient
from bobweb.bob.message_handler import handle_update
from bobweb.bob.telethon_client import start_telethon

logging_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
logging.basicConfig(format=logging_format, level=logging.DEBUG)  # NOSONAR
logger = logging.getLogger(__name__)


async def send_file_to_global_admin(file, bot):
    if database.get_global_admin() is not None:
        await bot.send_document(database.get_global_admin().id, file)
    else:
        await broadcast(bot, "Varmuuskopiointi pilveen epäonnistui, global_admin ei ole asetettu.")


def init_bot_application() -> Application:
    token = os.getenv("BOT_TOKEN")
    if token == "" or token is None:
        logger.critical("BOT_TOKEN env variable is not set. ")
        raise ValueError("BOT_TOKEN env variable is not set. ")
    print(token)

    # Create the Application with bot's token.
    application = Application.builder().token(token).build()

    # Add only message handler. Is invoked for EVERY update (message) including replies and message edits.
    # Default handler is use in non-blocking manner, i.e. each update is handled without waiting previous
    # handling to finish.
    application.add_handler(MessageHandler(filters.ALL, handle_update, block=False))

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


api_id = os.getenv("TG_CLIENT_API_ID")
api_hash = os.getenv("TG_CLIENT_API_HASH")
bot_token = os.getenv("BOT_TOKEN")

# Telethon Telegram Client
client = TelegramClient('anon', api_id, api_hash)


async def main() -> None:
    # Initiate bot application
    application: Application = init_bot_application()

    # Add scheduled tasks before starting polling
    scheduler.Scheduler(application)

    async with application:  # Calls `initialize` and `shutdown`
        await application.start()
        logger.info("Starting polling")
        await application.updater.start_polling()

        # Start other asyncio frameworks here
        # Add some logic that keeps the event loop running until you want to shutdown
        # Stop the other asyncio frameworks here

        await telethon_client.start_telethon()
        asyncio.create_task(telethon_client.client.run_until_disconnected())
        # async with client:
        #     # Getting information about yourself
        #     me = await client.get_me()
        #
        #     # "me" is a user object. You can pretty-print
        #     # any Telegram object with the "stringify" method:
        #     print(me.stringify())

        await application.updater.stop()
        await application.stop()

    logger.info("Application stopped")

    # Disconnect Telethon client connection
    telethon_client.client.disconnect()

    # As a last thing close http_client connection
    async_http.client.close()


if __name__ == '__main__':
    asyncio.run(main())

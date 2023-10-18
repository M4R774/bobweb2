#!/usr/bin/env python
import asyncio
import os
import logging

from telegram.ext import MessageHandler, CallbackQueryHandler, Application, filters
from telethon import TelegramClient

from bobweb.bob import scheduler, async_http
from bobweb.bob import command_service
from bobweb.bob.message_handler import handle_update

logging_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
logging.basicConfig(format=logging_format, level=logging.DEBUG)  # NOSONAR
logger = logging.getLogger(__name__)


# Remember to add your values to the environment variables
api_id = os.getenv("TG_CLIENT_API_ID")
api_hash = os.getenv("TG_CLIENT_API_HASH")
bot_token = os.getenv("BOT_TOKEN")


def init_telegram_client() -> TelegramClient | None:
    """ Returns initiated Telegram client or None """
    if api_id is None or api_hash is None:
        logger.warning("Telegram client api ID and api Hash environment variables are missing. Can not start Telethon "
                       "Telegram Client alongside Python Telegram Bot application. However bot can still be run "
                       "without Telegram client api")
        return None
    else:
        return TelegramClient('bot', int(api_id), api_hash)


# Telethon Telegram Client
telegram_client: TelegramClient | None = init_telegram_client()


def init_bot_application() -> Application:
    """ Initiate Telegram Python Bot application with its handlers"""
    if bot_token == "" or bot_token is None:
        logger.critical("BOT_TOKEN env variable is not set. ")
        raise ValueError("BOT_TOKEN env variable is not set. ")

    # Create the Application with bot's token.
    application = Application.builder().token(bot_token).build()

    # Add only message handler. Is invoked for EVERY update (message) including replies and message edits.
    # Default handler is use in non-blocking manner, i.e. each update is handled without waiting previous
    # handling to finish.
    application.add_handler(MessageHandler(filters.ALL, handle_update, block=False))

    # callback query is handled by command service
    application.add_handler(CallbackQueryHandler(command_service.instance.reply_and_callback_query_handler))

    # Add scheduled tasks
    scheduler.Scheduler(application)
    return application


async def start_telegram_client() -> TelegramClient:
    """ Connects Telethon Telegram client if required environment variables are set. This is not required, as only
        some functionalities require full telegram client connection. For easier development, bot can be run without
        any Telegram client env-variables """
    await telegram_client.start(bot_token=bot_token)
    me = await telegram_client.get_me()
    logger.info(f"Connected to Telegram client with user={me.username}")
    return telegram_client


async def run_ptb_application_and_telegram_client(application: Application) -> None:
    """ Run PTB application and all other asyncio application / scripts in the same event loop """
    async with application:  # Calls `initialize` on context enter and `shutdown` on context exit
        logger.info("Starting PTB bot application")
        await application.start()
        await application.updater.start_polling()

        # Start other asyncio frameworks and/or scripts here
        await start_telegram_client()
        # Some logic that keeps the event loop running until you want to shut down is required
        await telegram_client.run_until_disconnected()

        # Stop the other asyncio frameworks after this before PTB bot application and event loop is closed
        await application.updater.stop()
        await application.stop()


def main() -> None:
    # Initiate bot application
    application: Application = init_bot_application()

    if telegram_client is None:
        # If there is no telegram client to run in the same loop, run simple run_polling method that is blocking and
        # handles everything needed in the same call
        application.run_polling()
        application.updater.idle()
    else:
        # Run multiple asyncio applications in the same loop
        task = run_ptb_application_and_telegram_client(application)
        asyncio.run(task)

    logger.info("Application stopped")

    # Disconnect Telethon client connection
    if telegram_client and telegram_client.is_connected():
        telegram_client.disconnect()

    # As a last thing close http_client connection
    async_http.client.close()


if __name__ == '__main__':
    main()

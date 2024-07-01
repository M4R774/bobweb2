#!/usr/bin/env python
import asyncio
import logging

from telegram.ext import MessageHandler, Application, filters

from bobweb.bob import async_http, config
from bobweb.bob import command_service
from bobweb.bob.error_handler import error_handler
from bobweb.bob.message_handler import handle_update

logger = logging.getLogger(__name__)


def init_bot_application() -> Application:
    """ Initiate Telegram Python Bot application with its handlers"""
    bot_token = config.bot_token
    if bot_token == "" or bot_token is None:
        logger.critical("BOT_TOKEN env variable is not set.")
        raise ValueError("BOT_TOKEN env variable is not set.")

    # Create the Application with bot's token.
    application = Application.builder().token(bot_token).build()

    # Add only message handler. Is invoked for EVERY update (message) including replies and message edits.
    # Default handler is use in non-blocking manner, i.e. each update is handled without waiting previous
    # handling to finish.
    application.add_handler(MessageHandler(filters.ALL, handle_update, block=False))

    # Register general error handler that catches all uncaught errors
    application.add_error_handler(error_handler)

    return application


async def run_telethon_client_and_bot(application: Application) -> None:
    """ Run PTB application and Telethon client in the same event loop """

    async with application:
        logger.info("Starting PTB bot application")
        await application.start()
        await application.updater.start_polling()

        # Some logic that keeps the event loop running until you want to shut down is required
        client = await telethon_service.client.initialize_and_get_telethon_client()
        await client.run_until_disconnected()

        # Stop the other asyncio frameworks after this before PTB bot application and event loop is closed
        await application.updater.stop()
        await application.stop()


async def main() -> None:
    # Initiate bot application
    application: Application = init_bot_application()

    application.run_polling()
    application.updater.idle()

    # As a last thing close http_client connection
    async_http.client.close()


if __name__ == '__main__':
    asyncio.run(main())


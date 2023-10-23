#!/usr/bin/env python
import asyncio
import os
import logging

from telegram.ext import MessageHandler, CallbackQueryHandler, Application, filters

from bobweb.bob import scheduler, async_http, telethon_client
from bobweb.bob import command_service
from bobweb.bob.config import bot_token
from bobweb.bob.message_handler import handle_update

logging_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
logging.basicConfig(format=logging_format, level=logging.DEBUG)  # NOSONAR
logger = logging.getLogger(__name__)





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


async def run_telethon_client_and_bot(application: Application) -> None:
    """ Run PTB application and Telethon client in the same event loop """

    async with application:
        logger.info("Starting PTB bot application")
        await application.start()
        await application.updater.start_polling()

        # Some logic that keeps the event loop running until you want to shut down is required
        client = await telethon_client.get_client()
        await client.run_until_disconnected()

        # Stop the other asyncio frameworks after this before PTB bot application and event loop is closed
        await application.updater.stop()
        await application.stop()


def main() -> None:
    # Initiate bot application
    application: Application = init_bot_application()

    if not telethon_client.has_telegram_client():
        # If there is no telegram client to run in the same loop, run simple run_polling method that is blocking and
        # handles everything needed in the same call
        application.run_polling()
        application.updater.idle()
    else:
        # Run multiple asyncio applications in the same loop
        task = run_telethon_client_and_bot(application)
        asyncio.run(task)

    logger.info("Application stopped")

    # Disconnect Telethon client connection
    telethon_client.close()

    # As a last thing close http_client connection
    async_http.client.close()


if __name__ == '__main__':
    main()


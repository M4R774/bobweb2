#!/usr/bin/env python
import asyncio
import logging
from telegram.ext import MessageHandler, CallbackQueryHandler, Application, filters

from bobweb.bob import scheduler, async_http, telethon_service, config, twitch_service
from bobweb.bob import command_service
from bobweb.bob.error_handler import error_handler
from bobweb.bob.message_handler import handle_update
from bobweb.bob import pinned_notifications
from bobweb.bob.pinned_notifications import MessageBoardService

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

    # callback queries (messages inline keyboard button presses) are handled by command service
    application.add_handler(CallbackQueryHandler(command_service.instance.reply_and_callback_query_handler))

    # Register general error handler that catches all uncaught errors
    application.add_error_handler(error_handler)

    # Initialize all message boards
    pinned_notifications.instance = MessageBoardService(updater.bot)

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
        client = await telethon_service.client.initialize_and_get_telethon_client()
        await client.run_until_disconnected()

        # Stop the other asyncio frameworks after this before PTB bot application and event loop is closed
        await application.updater.stop()
        await application.stop()


async def main() -> None:
    # Initiate bot application
    application: Application = init_bot_application()

    if telethon_service.are_telegram_client_env_variables_set():
        # Run multiple asyncio applications in the same loop
        await asyncio.gather(
            run_telethon_client_and_bot(application),
            twitch_service.start_service()
        )
    else:
        # If there is no telegram client to run in the same loop, run simple run_polling method that is blocking and
        # handles everything needed in the same call
        application.run_polling()
        application.updater.idle()

    # Disconnect Telethon client connection
    telethon_service.client.close()

    # As a last thing close http_client connection
    async_http.client.close()


if __name__ == '__main__':
    asyncio.run(main())


#!/usr/bin/env python
import asyncio
import logging

from aiohttp import web
from telegram.ext import MessageHandler, CallbackQueryHandler, Application, filters, BaseRateLimiter, AIORateLimiter

from bobweb.bob import scheduler, async_http, telethon_service, config, twitch_service
from bobweb.bob import command_service
from bobweb.bob.error_handler import unhandled_bot_exception_handler
from bobweb.bob.message_handler import handle_update
from bobweb.bob import message_board_service

logger = logging.getLogger(__name__)


def init_bot_application() -> Application:
    """ Initiate Telegram Python Bot application with its handlers"""
    bot_token = config.bot_token
    if bot_token == "" or bot_token is None:
        logger.critical("BOT_TOKEN env variable is not set.")
        raise ValueError("BOT_TOKEN env variable is not set.")

    # Create the Application with bot's token.
    # Rate limiter is used to prevent flooding related errors (too many updates to Telegram server in a short period).
    #
    application = (Application.builder()
                   .token(bot_token)
                   .rate_limiter(AIORateLimiter(max_retries=5, group_max_rate=30))
                   .connect_timeout(30)
                   .pool_timeout(30)
                   .read_timeout(30)
                   .write_timeout(30)
                   .media_write_timeout(30)
                   .get_updates_connect_timeout(10)
                   .get_updates_read_timeout(10)
                   .get_updates_write_timeout(15)
                   .get_updates_connection_pool_size(5)
                   .get_updates_pool_timeout(5)
                   .build())

    # Add only message handler. Is invoked for EVERY update (message) including replies and message edits.
    # Default handler is use in non-blocking manner, i.e. each update is handled without waiting previous
    # handling to finish.
    application.add_handler(MessageHandler(filters.ALL, handle_update, block=False))

    # callback queries (messages inline keyboard button presses) are handled by command service
    application.add_handler(CallbackQueryHandler(command_service.instance.reply_and_callback_query_handler))

    # Register general error handler that catches all uncaught errors
    application.add_error_handler(unhandled_bot_exception_handler)

    # Create message board service instance
    message_board_service.instance = message_board_service.MessageBoardService(application)

    # Add scheduled tasks and add asynchronous startup tasks to be run when the application is started
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
            run_web_server(),
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


async def run_web_server():
    app = web.Application()
    app.add_routes([web.get('/', hello_word_handler)])

    runner = web.AppRunner(app)
    await runner.setup()
    port = 5000
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    print(f"Web server started at port: {5000}. Try: http://localhost:{port}/")


async def hello_word_handler(request):
    return web.Response(text="Hello, World!")


if __name__ == '__main__':
    asyncio.run(main())


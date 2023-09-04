#!/usr/bin/env python
import asyncio
import os
import logging

from asgiref.sync import sync_to_async
from telegram.ext import MessageHandler, CallbackQueryHandler, Application, filters

from bobweb.bob import scheduler, message_handler_voice
from bobweb.bob import database
from bobweb.bob import command_service
from bobweb.bob.broadcaster import broadcast
from bobweb.bob.git_promotions import broadcast_and_promote
from bobweb.bob.message_handler import handle_update

logging_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
logging.basicConfig(format=logging_format, level=logging.DEBUG)  # NOSONAR
logger = logging.getLogger(__name__)


async def send_file_to_global_admin(file, bot):
    if database.get_global_admin() is not None:
        await bot.send_document(database.get_global_admin().id, file)
    else:
        await broadcast(bot, "Varmuuskopiointi pilveen epäonnistui, global_admin ei ole asetettu.")


def init_bot():
    token = os.getenv("BOT_TOKEN")
    if token == "" or token is None:
        logger.critical("BOT_TOKEN env variable is not set. ")
        raise ValueError("BOT_TOKEN env variable is not set. ")
    print(token)

    # Create the Application with bot's token.
    application = Application.builder().token(token).build()

    # Initialize all command handlers
    command_service_instance = command_service.instance

    # on different commands - answer in Telegram
    # is invoked for EVERY update (message) including replies and message edits
    application.add_handler(MessageHandler(filters.ALL, handle_update))

    # callback query is handled by command service
    application.add_handler(CallbackQueryHandler(command_service_instance.reply_and_callback_query_handler))

    notify_if_ffmpeg_not_available()

    return application


def notify_if_ffmpeg_not_available():
    if not message_handler_voice.ffmpeg_available:
        warning = 'NOTE! ffmpeg program not available. Command depending on video- and/or ' \
                  'audio conversion won\'t work. To enable, install ffmpeg and make it runnable' \
                  'from the terminal / command prompt.'
        logger.warning(warning)


async def broadcast_and_promote_and_start_application(application: Application):
    await broadcast_and_promote(application.bot)
    await application.initialize()
    await application.start()


def main() -> None:
    application = init_bot()
    asyncio.get_event_loop().run_until_complete(
        # Initialize broadcast and promote features and start the bot
        broadcast_and_promote_and_start_application(application)
    )
    scheduler.Scheduler(application)  # Initiate scheduled jobs
    application.run_polling()  # Start polling for new messages (updates) from Telegram server


if __name__ == '__main__':
    main()

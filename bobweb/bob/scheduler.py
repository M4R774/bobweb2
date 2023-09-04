import datetime
import logging

from telegram.constants import ParseMode
from telegram.ext import Application, CallbackContext
import signal  # Keyboard interrupt listening for Windows

from bobweb.bob.command_epic_games import create_free_games_announcement_msg, fetch_failed_msg
from bobweb.bob.git_promotions import broadcast_and_promote
from bobweb.bob.resources.bob_constants import fitz
from bobweb.bob.utils_common import has

signal.signal(signal.SIGINT, signal.SIG_DFL)

from bobweb.bob import database, broadcaster, nordpool_service
from bobweb.bob import db_backup

logger = logging.getLogger(__name__)


"""Telegram JobQue daily runs days are given as tuple of week day 
   indexes starting from 0. These are common presets
"""
MONDAY = (0,)
TUESDAY = (1,)
WEDNESDAY = (2,)
THURSDAY = (3,)
FRIDAY = (4,)
SATURDAY = (5,)
EVERY_WEEK_DAY = (0, 1, 2, 3, 4, 5, 6)


class Scheduler:
    """
    Class for all scheduled task and background services.

    Since update 13.0 -> 20.5 all scheduled tasks are handled with PTB library's JobQueue
    Documentation: https://docs.python-telegram-bot.org/en/v20.5/telegram.ext.jobqueue.html

    Example:
    “Every day at 08:00.”
        application.job_queue.run_daily(days=EVERY_WEEK_DAY, time=datetime.time(hour=8, minute=0, tzinfo=fitz),
                                        callback=self.good_morning_broadcast)

    Where the call back would be:
        async def good_morning_broadcast(self):
            await broadcaster.broadcast(self.updater.bot, "HYVÄÄ HUOMENTA!")
    """
    def __init__(self, application: Application):
        # First invoke all jobs that should be run at startup and then add recurrent tasks
        # At the startup do broadcast and promote action immediately once
        application.job_queue.run_once(broadcast_and_promote, 0)

        # 'At 18:05 on Thursday.'
        application.job_queue.run_daily(days=THURSDAY, time=datetime.time(hour=18, minute=5, tzinfo=fitz),
                                        callback=announce_free_epic_games_store_games)

        # “At 17:00 on Friday.”
        application.job_queue.run_daily(days=FRIDAY, time=datetime.time(hour=17, minute=0, tzinfo=fitz),
                                        callback=friday_noon)

        # Every midnight empy SahkoCommand cache
        application.job_queue.run_daily(days=EVERY_WEEK_DAY, time=datetime.time(hour=0, minute=0, tzinfo=fitz),
                                        callback=nordpool_service.cleanup_cache)
        logger.info("Scheduled tasks started")


async def friday_noon(context: CallbackContext):
    await db_backup.create(context.bot)
    await broadcaster.broadcast(context.bot, "Jahas, työviikko taas pulkassa,,,")


async def announce_free_epic_games_store_games(context: CallbackContext):
    chats_with_announcement_on = [x for x in database.get_chats() if x.free_game_offers_enabled]
    if len(chats_with_announcement_on) == 0:
        return  # Early return if no chats with

    # Define either announcement message and possible game images or fetch_failed_msg without image
    try:
        msg, image_bytes = create_free_games_announcement_msg()
    except Exception as e:
        msg, image_bytes = fetch_failed_msg, None
        logger.error(e)

    for chat in chats_with_announcement_on:
        if has(image_bytes):
            await context.bot.send_photo(chat_id=chat.id, photo=image_bytes, caption=msg, parse_mode=ParseMode.HTML)
        else:
            await context.bot.send_message(chat_id=chat.id, text=msg, parse_mode=ParseMode.HTML)

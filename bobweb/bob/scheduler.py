import datetime
import logging

from telegram.ext import Application, CallbackContext
import signal  # Keyboard interrupt listening for Windows

from bobweb.bob.command_epic_games import daily_announce_new_free_epic_games_store_games
from bobweb.bob.git_promotions import broadcast_and_promote
from bobweb.bob.resources.bob_constants import fitz

signal.signal(signal.SIGINT, signal.SIG_DFL)

from bobweb.bob import broadcaster, nordpool_service, twitch_service, message_board_service
from bobweb.bob import db_backup

logger = logging.getLogger(__name__)


"""Telegram JobQue daily runs days are given as tuple of week day 
   indexes on which days the job is run. These are common presets.
   0 = Sunday, 1 = Monday ... 6 = Saturday 
   https://docs.python-telegram-bot.org/en/v20.5/telegram.ext.jobqueue.html
"""
MONDAY = (1,)
TUESDAY = (2,)
WEDNESDAY = (3,)
THURSDAY = (4,)
FRIDAY = (5,)
SATURDAY = (6,)
SUNDAY = (0,)
EVERY_WEEK_DAY = (0, 1, 2, 3, 4, 5, 6)


class Scheduler:
    """
    Class for all scheduled task and background services. Note that timezone info is defined in each schedule.

    Since update 13.0 -> 20.5 all scheduled tasks are handled with PTB library's JobQueue
    JobQueue documentation: https://docs.python-telegram-bot.org/en/v20.5/telegram.ext.jobqueue.html

    Cron syntax codumentation: https://apscheduler.readthedocs.io/en/stable/modules/triggers/cron.html

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
        application.job_queue.run_once(start_message_board_service, 5)

        # Every day at 18:00:30
        application.job_queue.run_daily(days=EVERY_WEEK_DAY,
                                        time=datetime.time(hour=18, minute=0, second=30, tzinfo=fitz),
                                        callback=daily_announce_new_free_epic_games_store_games)

        # At 17:00 on Friday
        application.job_queue.run_daily(days=FRIDAY,
                                        time=datetime.time(hour=17, minute=0, tzinfo=fitz),
                                        callback=friday_noon)

        # Every midnight empy SahkoCommand cache
        application.job_queue.run_daily(days=EVERY_WEEK_DAY,
                                        time=datetime.time(hour=0, minute=0, tzinfo=fitz),
                                        callback=nordpool_service.cleanup_cache)

        logger.info("Scheduled tasks added to the job queue")


async def start_message_board_service(context: CallbackContext = None):
    await message_board_service.instance.update_boards_and_schedule_next_update()


async def friday_noon(context: CallbackContext):
    await db_backup.create(context.bot)
    await broadcaster.broadcast(context.bot, "Jahas, työviikko taas pulkassa,,,")

import datetime
import logging

from telegram._utils.types import JSONDict
from telegram.ext import Application, CallbackContext
import signal  # Keyboard interrupt listening for Windows

from bot import main, broadcaster, nordpool_service, message_board_service
from bot import db_backup
from bot.commands.epic_games import daily_announce_new_free_epic_games_store_games
from bot.git_promotions import broadcast_and_promote
from bot.resources.bob_constants import fitz

signal.signal(signal.SIGINT, signal.SIG_DFL)

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

# Parameter 'misfire_grace_time' defines time window in seconds in which the job is run if initial time was missed.
# Value 'None' means, that grace period is infinite.
# More info: https://apscheduler.readthedocs.io/en/latest/modules/job.html
default_job_props: JSONDict = {
    'misfire_grace_time': 60
}


def schedule_jobs(application: Application):
    """
    Schedules all bots scheduled jobs. Note that timezone info is defined in each schedule.

    Since update 13.0 -> 20.5 all scheduled tasks are handled with PTB library's JobQueue
    JobQueue documentation: https://docs.python-telegram-bot.org/en/v20.5/telegram.ext.jobqueue.html
    Cron syntax codumentation: https://apscheduler.readthedocs.io/en/stable/modules/triggers/cron.html

    APScheduler docs: https://apscheduler.readthedocs.io/en/latest/index.html

    Example:
    “Every day at 08:00.”
        application.job_queue.run_daily(days=EVERY_WEEK_DAY, time=datetime.time(hour=8, minute=0, tzinfo=fitz),
                                        callback=self.good_morning_broadcast)

    Where the call back would be:
        async def good_morning_broadcast(self):
            await broadcaster.broadcast(self.updater.bot, "HYVÄÄ HUOMENTA!")


    """

    # First invoke all jobs that should be run at startup and then add recurrent tasks.
    # Startup tasks are done after delay (in seconds) so that the bot has time to first start up
    application.job_queue.run_once(broadcast_and_promote, 0, job_kwargs=default_job_props)
    application.job_queue.run_once(start_message_board_service, 5, job_kwargs=default_job_props)

    # Every day at 18:00:30
    application.job_queue.run_daily(days=EVERY_WEEK_DAY,
                                    time=datetime.time(hour=18, minute=0, second=30, tzinfo=fitz),
                                    callback=daily_announce_new_free_epic_games_store_games,
                                    job_kwargs=default_job_props)

    # At 17:00 on Friday
    application.job_queue.run_daily(days=FRIDAY,
                                    time=datetime.time(hour=17, minute=0, tzinfo=fitz),
                                    callback=backup_with_end_of_work_week_greeting,
                                    job_kwargs=default_job_props)

    # Every midnight empy SahkoCommand cache
    application.job_queue.run_daily(days=EVERY_WEEK_DAY,
                                    time=datetime.time(hour=0, minute=0, tzinfo=fitz),
                                    callback=nordpool_service.cleanup_cache,
                                    job_kwargs=default_job_props)

    logger.info("Scheduled tasks added to the job queue")


async def start_message_board_service(context: CallbackContext = None):
    await message_board_service.instance.update_boards_and_schedule_next_update()


async def backup_with_end_of_work_week_greeting(context: CallbackContext):
    await db_backup.create(context.bot)
    await broadcaster.broadcast(context.bot, "Jahas, työviikko taas pulkassa,,,")

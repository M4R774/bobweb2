import aiocron
import asyncio

import pytz
from telegram.ext import Updater
import signal  # Keyboard interrupt listening for Windows

from bobweb.bob.resources.bob_constants import DEFAULT_TIMEZONE

signal.signal(signal.SIGINT, signal.SIG_DFL)

from bobweb.bob import main
from bobweb.bob import db_backup


class Scheduler:
    def __init__(self, updater: Updater):
        self.updater = updater

        # Nice website for building cron schedules: https://crontab.guru/#0_16_*_*_5
        # NOTE: Seconds is the LAST element, while minutes is the FIRST
        # eg. minute hour day(month) month day(week) second

        tz = pytz.timezone(DEFAULT_TIMEZONE)

        cron_friday_noon = '0 17 * * 5'  # “At 17:00 on Friday.”
        self.friday_noon_task = aiocron.crontab(str(cron_friday_noon),
                                                func=self.friday_noon,
                                                start=True,
                                                tz=tz)

        cron_every_morning = '0 8 * * *'  # “Every day at 08:00.”
        self.friday_noon_task = aiocron.crontab(str(cron_every_morning),
                                                func=self.good_morning_broadcast,
                                                start=True,
                                                tz=tz)

        asyncio.get_event_loop().run_forever()

    async def friday_noon(self):
        # TODO: Perjantain rankkien lähetys
        await db_backup.create(self.updater.bot)
        await main.broadcast(self.updater.bot, "Jahas, työviikko taas pulkassa,,,")

    async def good_morning_broadcast(self):
        # TODO: Daily digest
        await main.broadcast(self.updater.bot, "HYVÄÄ HUOMENTA!")

    #TODO: Muistutus feature

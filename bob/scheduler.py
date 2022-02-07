import aiocron
import asyncio

from asgiref.sync import sync_to_async
from telegram.ext import Updater

import main

# TODO: Keyboard interrupt listening


class Scheduler:
    def __init__(self, updater: Updater):
        self.updater = updater

    # Nice website for building cron schedules: https://crontab.guru/#0_16_*_*_5
    # NOTE: Seconds is the LAST element, while minutes is the FIRST
    # eg. minute hour day(month) month day(week) second
        @sync_to_async
        @aiocron.crontab('0 16 * * 5')  # '0 16 * * 5' = “At 16:00 on Friday.”
        async def yourcouritine():
            await main.broadcast(self.updater.bot, "Absurdia")
            print('Hello world')

        #@aiocron.crontab('* * * * * */5')  # '0 16 * * 5' = “Every 5 seconds”
        #async def yourcouritine2():
        #    await main.broadcast(self.updater.bot, "Absurdia")
        #    print('Heippa maailma')

        asyncio.get_event_loop().run_forever()

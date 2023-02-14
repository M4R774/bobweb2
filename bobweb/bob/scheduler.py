import logging

import aiocron
import asyncio

from telegram import ParseMode
from telegram.ext import Updater
import signal  # Keyboard interrupt listening for Windows

from bobweb.bob.command_epic_games import create_free_games_announcement_msg, fetch_failed_msg
from bobweb.bob.resources.bob_constants import fitz
from bobweb.bob.utils_common import has

signal.signal(signal.SIGINT, signal.SIG_DFL)

from bobweb.bob import database, broadcaster
from bobweb.bob import db_backup

logger = logging.getLogger(__name__)

class Scheduler:
    def __init__(self, updater: Updater):
        self.updater: Updater = updater

        # Nice website for building cron schedules: https://crontab.guru/#0_16_*_*_5
        # NOTE: Seconds is the LAST element, while minutes is the FIRST
        # eg. minute hour day(month) month day(week) second
        #
        # For example:
        # cron_every_morning = '0 8 * * *'  # “Every day at 08:00.”
        # self.friday_noon_task = aiocron.crontab(str(cron_every_morning),
        #                                         func=self.good_morning_broadcast,
        #                                         start=True,
        #                                         tz=tz)
        #
        # async def good_morning_broadcast(self):
        #     await main.broadcast(self.updater.bot, "HYVÄÄ HUOMENTA!")
        cron_every_thursday_at_18_05 = '05 18 * * 4'  # 'At 18:05 on Thursday.'
        aiocron.crontab(cron_every_thursday_at_18_05,
                        func=self.announce_free_epic_games_store_games,
                        start=True,
                        tz=fitz)

        cron_friday_noon = '0 17 * * 5'  # “At 17:00 on Friday.”
        aiocron.crontab(cron_friday_noon,
                        func=self.friday_noon,
                        start=True,
                        tz=fitz)

        asyncio.get_event_loop().run_forever()

    async def friday_noon(self):
        # TODO: Perjantain rankkien lähetys
        await db_backup.create(self.updater.bot)
        await broadcaster.broadcast(self.updater.bot, "Jahas, työviikko taas pulkassa,,,")

    async def announce_free_epic_games_store_games(self):
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
                self.updater.bot.send_photo(chat_id=chat.id, photo=image_bytes, caption=msg, parse_mode=ParseMode.HTML)
            else:
                self.updater.bot.send_message(chat_id=chat.id, text=msg, parse_mode=ParseMode.HTML)

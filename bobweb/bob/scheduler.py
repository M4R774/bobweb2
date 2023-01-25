import json
from datetime import datetime

import aiocron
import asyncio

import pytz
import requests
from requests import Response
from telegram.ext import Updater
import signal  # Keyboard interrupt listening for Windows

from bobweb.bob.resources.bob_constants import fitz
from bobweb.bob.utils_common import flatten, flatten_single

signal.signal(signal.SIGINT, signal.SIG_DFL)

from bobweb.bob import main
from bobweb.bob import db_backup


class Scheduler:
    def __init__(self, updater: Updater):
        self.updater = updater

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
        cron_every_thursday_at_20 = '0 20 * * 4'  # 'At 20:00 on Thursday.'
        cron_friday_noon = '0 17 * * 5'  # “At 17:00 on Friday.”
        aiocron.crontab(cron_friday_noon,
                        func=self.friday_noon,
                        start=True,
                        tz=fitz)

        asyncio.get_event_loop().run_forever()

    async def friday_noon(self):
        # TODO: Perjantain rankkien lähetys
        await db_backup.create(self.updater.bot)
        await main.broadcast(self.updater.bot, "Jahas, työviikko taas pulkassa,,,")


def fetch_free_epic_games_offering():
    res: Response = requests.get(epic_free_games_base_url)
    if res.status_code != 200:
        # await main.broadcast(self.updater.bot, 'Ilmaisten eeppisten pelien haku epäonnistui 🔌✂️')
        return

    content: dict = res.json()

    # use None-safe dict-get-chain that returns list if any key is not found
    game_dict_list = content.get('data', {}).get('Catalog', {}).get('searchStore', {}).get('elements', [])

    game_offers = []
    for d in game_dict_list:
        game_offer: EpicGamesGameOffer = extract_game_offer_from_game_dict(d)
        if game_offer is not None:
            game_offers.append(game_offer)

    list(game_offers)


class EpicGamesGameOffer:
    def __init__(self,
                 title: str,
                 description: str,
                 starts_at: datetime,
                 ends_at: datetime,
                 page_slug: str,
                 image_tall_url: str,
                 image_thumbnail_url: str):
        self.title = title
        self.description = description
        self.starts_at = starts_at
        self.ends_at = ends_at
        self.page_slug = page_slug
        self.image_tall_url = image_tall_url
        self.image_thumbnail_url = image_thumbnail_url


def extract_game_offer_from_game_dict(d: dict) -> EpicGamesGameOffer | None:
    image_urls = {}
    for img_obj in d.get('keyImages', []):
        image_urls[img_obj['type']] = img_obj['url']

    # To get all promotions, concatenate active promotionalOffers with upcomingPromotional offers
    promotions_layer_1: dict = d.get('promotions', {}) or {}
    promotions_layer_2: list = promotions_layer_1.get('promotionalOffers', [])
    promotions = flatten_single([promotion['promotionalOffers'] for promotion in promotions_layer_2])

    if len(promotions) == 0:
        return None

    return EpicGamesGameOffer(
        title=d.get('title'),
        description=d.get('description'),
        starts_at=promotions[0]['startDate'],
        ends_at=promotions[0]['endDate'],
        page_slug=d.get('offerMappings')[0].get('pageSlug'),
        image_tall_url=image_urls.get('OfferImageTall'),
        image_thumbnail_url=image_urls.get('Thumbnail'),
    )


epic_free_games_base_url = 'https://store-site-backend-static.ak.epicgames.com/freeGamesPromotions?locale=en-US&country=FI&allowCountries=FI'

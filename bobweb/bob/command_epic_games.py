import io
import logging
from datetime import datetime
from typing import Tuple, List

import aiohttp
from PIL import Image
from aiohttp import ClientResponseError, ClientSession
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import CallbackContext

from bobweb.bob import utils_common
from bobweb.bob.command import ChatCommand, regex_simple_command
from bobweb.bob.command_image_generation import image_to_byte_array
from bobweb.bob.utils_common import fitzstr_from, has, flatten, dict_search

logger = logging.getLogger(__name__)


class EpicGamesOffersCommand(ChatCommand):

    def __init__(self):
        super(EpicGamesOffersCommand, self).__init__(
            name='epicgames',
            regex=regex_simple_command('epicgames'),
            help_text_short=('!epicgames', 'ilmaispelit')
        )

    async def handle_update(self, update: Update, context: CallbackContext = None) -> None:
        try:
            msg, image_bytes = await create_free_games_announcement_msg()
            if has(image_bytes):
                await update.effective_message.reply_photo(photo=image_bytes, caption=msg, parse_mode=ParseMode.HTML, quote=False)
            else:
                await update.effective_message.reply_text(text=msg, parse_mode=ParseMode.HTML, quote=False)
        except ClientResponseError as e:
            log_msg = f'Epic Games Api error. [status]: {str(e.status)}, [message]: {e.message}, [headers]: {e.headers}'
            logger.exception(log_msg, exc_info=True)
            await update.effective_message.reply_text(fetch_failed_msg, quote=False)


fetch_failed_msg = 'Ilmaisten eeppisten pelien haku epäonnistui 🔌✂️'
fetch_ok_no_free_games = 'Ilmaisia eeppisiä pelejä ei ole tällä hetkellä tarjolla 👾'
epic_free_games_api_endpoint = 'https://store-site-backend-static.ak.epicgames.com/freeGamesPromotions?country=FI'
epic_games_store_product_base_url = 'https://store.epicgames.com/en-US/p/'
epic_games_store_free_games_page_url = 'https://store.epicgames.com/en-US/free-games'


class EpicGamesOffer:
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
        self.vertical_img_url = image_tall_url
        self.horizontal_img_url = image_thumbnail_url


async def create_free_games_announcement_msg() -> tuple[str, bytes | None]:
    async with aiohttp.ClientSession() as session:  # All requests are done with the same session open
        games = await fetch_free_epic_games_offering(session)
        if len(games) == 0:
            return fetch_ok_no_free_games, None
        else:
            heading = '📬 Viikon ilmaiset eeppiset pelit 📩'
            msg = heading + format_games_offer_list(games)
            msg_image = await get_game_offers_image(games, session)
            image_bytes = image_to_byte_array(msg_image)
            return msg, image_bytes


def format_games_offer_list(games: list[EpicGamesOffer]):
    game_list = ''
    for game in games:
        # Telegram html style: https://core.telegram.org/bots/api#html-style
        # Html is used as it does not require escaping dashes from game.page_slug values
        header_with_link = f'🕹 <b><a href="{get_product_page_or_deals_page_url(game.page_slug)}">{game.title}</a></b>'
        promotion_duration = f'{fitzstr_from(game.starts_at)} - {fitzstr_from(game.ends_at)}'
        game_list += f'\n\n{header_with_link} {promotion_duration}\n{game.description}'
    return game_list


async def fetch_free_epic_games_offering(session: ClientSession) -> list[EpicGamesOffer]:
    content: dict = await utils_common.fetch_json_with_session(epic_free_games_api_endpoint, session)
    # use None-safe dict-get-chain that returns list if any key is not found
    game_dict_list = dict_search(content, 'data', 'Catalog', 'searchStore', 'elements') or []

    game_offers = []
    for d in game_dict_list:
        game_offer: EpicGamesOffer = extract_free_game_offer_from_game_dict(d)
        if game_offer is not None:
            game_offers.append(game_offer)

    return game_offers


async def get_game_offers_image(games: list[EpicGamesOffer], session: ClientSession) -> Image:
    # Get vertical image for each
    urls = create_list_of_offer_image_urls(games)
    fetched_bytes: Tuple[bytes] = await utils_common.fetch_all_content_bytes(urls, session)
    images: List[Image] = [Image.open(io.BytesIO(b)) for b in fetched_bytes]
    return create_image_collage(images)


def create_list_of_offer_image_urls(games: list[EpicGamesOffer]) -> List[str]:
    urls = []
    for game in games:
        url = game.horizontal_img_url if len(games) == 1 else game.vertical_img_url
        if has(url):
            urls.append(url)
    return urls


def get_product_page_or_deals_page_url(page_slug: str):
    if has(page_slug):
        return epic_games_store_product_base_url + page_slug
    else:
        return epic_games_store_free_games_page_url


def create_image_collage(images: list[Image]) -> Image:
    collage_width = sum([x.width for x in images])
    collage_height = min([x.height for x in images])

    canvas = Image.new('RGB', (collage_width, collage_height))
    next_x_coordinate = 0
    for i, image in enumerate(images):
        canvas.paste(image, (next_x_coordinate, 0))
        next_x_coordinate += image.width
    return canvas


def extract_free_game_offer_from_game_dict(d: dict) -> EpicGamesOffer | None:
    image_urls = {}
    for img_obj in d.get('keyImages', []):
        image_urls[img_obj['type']] = img_obj['url']

    # To get all promotions, concatenate active promotionalOffers with upcomingPromotional offers
    # Example result json in 'bobweb/bob/resources/test/epicGamesFreeGamesPromotionsExample.json'

    current_promotions: list = dict_search(d, 'promotions', 'promotionalOffers') or []
    promotional_offers = [promotion['promotionalOffers'] for promotion in current_promotions]
    items_promotions = flatten(promotional_offers)

    is_free = dict_search(d, 'price', 'totalPrice', 'discountPrice') == 0

    if len(items_promotions) == 0 or not is_free:
        return None

    datetime_format = '%Y-%m-%dT%H:%M:%S.%fZ'
    return EpicGamesOffer(
        title=d.get('title'),
        description=d.get('description'),
        starts_at=datetime.strptime(items_promotions[0]['startDate'], datetime_format),
        ends_at=datetime.strptime(items_promotions[0]['endDate'], datetime_format),
        page_slug=get_page_slug(d),
        image_tall_url=image_urls.get('OfferImageTall'),
        image_thumbnail_url=image_urls.get('Thumbnail'),
    )


def get_page_slug(data: dict):
    # try all known paths and return first non-None result
    return dict_search(data, 'catalogNs', 'mappings', 0, 'pageSlug') \
           or dict_search(data, 'offerMappings', 0, 'pageSlug')






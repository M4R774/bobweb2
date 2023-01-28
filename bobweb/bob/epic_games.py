import io
import logging
from datetime import datetime

import requests
from PIL import Image
from requests import Response
from telegram import Update
from telegram.ext import CallbackContext

from bobweb.bob.command import ChatCommand
from bobweb.bob.command_dallemini import image_to_byte_array
from bobweb.bob.resources.bob_constants import PREFIXES_MATCHER
from bobweb.bob.utils_common import fitzstr_from, has, flatten

logger = logging.getLogger(__name__)


class EpicGamesOffersCommand(ChatCommand):
    run_async = True  # Should be asynchronous

    def __init__(self):
        super(EpicGamesOffersCommand, self).__init__(
            name='epicgames',
            regex=rf'(?i)^{PREFIXES_MATCHER}epicgames$',  # case insensitive
            help_text_short=('!epicgames', 'ilmaispelit')
        )

    def handle_update(self, update: Update, context: CallbackContext = None) -> None:
        try:
            msg, image_bytes = create_free_games_announcement_msg()
            if has(image_bytes):
                update.effective_message.reply_photo(photo=image_bytes, caption=msg, parse_mode='html', quote=False)
            else:
                update.effective_message.reply_text(text=msg, parse_mode='html', quote=False)
        except Exception as e:
            logger.error(e)
            update.effective_message.reply_text(fetch_failed_msg, quote=False)


fetch_failed_msg = 'Ilmaisten eeppisten pelien haku epäonnistui 🔌✂️'
fetch_ok_no_free_games = 'Ilmaisia eeppisiä pelejä ei ole tällä hetkellä tarjolla 👾'
epic_free_games_api_endpoint = 'https://store-site-backend-static.ak.epicgames.com/freeGamesPromotions?country=FI'
epic_games_store_product_base_url = 'https://store.epicgames.com/en-US/p/'


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


def create_free_games_announcement_msg() -> tuple[str, bytes | None]:
    games = fetch_free_epic_games_offering()
    if len(games) == 0:
        return fetch_ok_no_free_games, None
    else:
        heading = '📬 Viikon ilmaiset eeppiset pelit 📩'
        msg = heading + format_games_offer_list(games)
        msg_image = get_game_offers_image(games)
        image_bytes = image_to_byte_array(msg_image)
        return msg, image_bytes


def format_games_offer_list(games: list[EpicGamesOffer]):
    game_list = ''
    for game in games:
        # Telegram html style: https://core.telegram.org/bots/api#html-style
        # Html is used as it does not require escaping dashes from game.page_slug values
        header_with_link = f'🕹 <b><a href="{epic_games_store_product_base_url + game.page_slug}">{game.title}</a></b>'
        promotion_duration = f'{fitzstr_from(game.starts_at)} - {fitzstr_from(game.ends_at)}'
        game_list += f'\n\n{header_with_link} {promotion_duration}\n{game.description}'
    return game_list


def fetch_free_epic_games_offering() -> list[EpicGamesOffer]:
    res: Response = requests.get(epic_free_games_api_endpoint)
    if res.status_code != 200:
        raise Exception('Epic Games Api error. Request got res with status: ' + str(res.status_code))

    content: dict = res.json()
    # use None-safe dict-get-chain that returns list if any key is not found
    game_dict_list = content.get('data', {}).get('Catalog', {}).get('searchStore', {}).get('elements', [])

    game_offers = []
    for d in game_dict_list:
        game_offer: EpicGamesOffer = extract_free_game_offer_from_game_dict(d)
        if game_offer is not None:
            game_offers.append(game_offer)

    return game_offers


def get_game_offers_image(games: list[EpicGamesOffer]) -> Image:
    # Get vertical image for each
    images = []
    for game in games:
        url = game.horizontal_img_url if len(games) == 0 else game.vertical_img_url
        if has(url):
            res = requests.get(url, stream=True)
            data = res.content
            images.append(Image.open(io.BytesIO(data)))
    return create_image_collage(images)


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
    promotions: dict = d.get('promotions', {}) or {}
    current_or_upcoming: list = promotions.get('promotionalOffers') or promotions.get('upcomingPromotionalOffers') or []
    items_promotions = flatten([promotion['promotionalOffers'] for promotion in current_or_upcoming])

    is_free = d.get('price', {}).get('totalPrice', {}).get('discountPrice', None) == 0

    if len(items_promotions) == 0 or not is_free:
        return None

    datetime_format = '%Y-%m-%dT%H:%M:%S.%fZ'
    return EpicGamesOffer(
        title=d.get('title'),
        description=d.get('description'),
        starts_at=datetime.strptime(items_promotions[0]['startDate'], datetime_format),
        ends_at=datetime.strptime(items_promotions[0]['endDate'], datetime_format),
        page_slug=d.get('offerMappings')[0].get('pageSlug'),
        image_tall_url=image_urls.get('OfferImageTall'),
        image_thumbnail_url=image_urls.get('Thumbnail'),
    )





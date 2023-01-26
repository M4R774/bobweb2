import io
from datetime import datetime

import requests
from PIL import Image
from requests import Response

from bobweb.bob.utils_common import flatten_single

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
        self.image_tall_url = image_tall_url
        self.image_thumbnail_url = image_thumbnail_url


def create_free_games_announcement_msg():
    games = fetch_free_epic_games_offering()

    # Telegram html style: https://core.telegram.org/bots/api#html-style
    # Html is used as it is easier that to escape telegram's Markdown syntax special characters from page_slug values
    msg = '📬 Viikon ilmaiset eeppiset pelit 📩\n\n'
    for game in games:
        game_section = f'🕹 <b><a href="{epic_games_store_product_base_url + game.page_slug}">{game.title}</a></b>\n' \
                        f'{(game.description.split(".", 1)[0] + ".") or game.description}\n\n'
        msg += game_section

    game_images = get_game_offers_image(games)
    return msg, game_images




def fetch_free_epic_games_offering() -> list[EpicGamesOffer]:
    res: Response = requests.get(epic_free_games_api_endpoint)
    if res.status_code != 200:
        # await main.broadcast(self.updater.bot, 'Ilmaisten eeppisten pelien haku epäonnistui 🔌✂️')
        return

    content: dict = res.json()

    # use None-safe dict-get-chain that returns list if any key is not found
    game_dict_list = content.get('data', {}).get('Catalog', {}).get('searchStore', {}).get('elements', [])

    game_offers = []
    for d in game_dict_list:
        game_offer: EpicGamesOffer = extract_game_offer_from_game_dict(d)
        if game_offer is not None:
            game_offers.append(game_offer)

    return game_offers


def get_game_offers_image(games: list[EpicGamesOffer]) -> Image:
    if len(games) == 1:
        # Get only horizontal image
        res = requests.get(games[0].image_thumbnail_url, stream=True)
        data = res.content
        return Image.open(io.BytesIO(data))

    elif len(games) > 1:
        # Get vertical image for each
        images = []
        for game in games:
            res = requests.get(game.image_tall_url, stream=True)
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


def extract_game_offer_from_game_dict(d: dict) -> EpicGamesOffer | None:
    image_urls = {}
    for img_obj in d.get('keyImages', []):
        image_urls[img_obj['type']] = img_obj['url']

    # To get all promotions, concatenate active promotionalOffers with upcomingPromotional offers
    promotions_layer_1: dict = d.get('promotions', {}) or {}
    promotions_layer_2: list = promotions_layer_1.get('promotionalOffers', [])
    promotions = flatten_single([promotion['promotionalOffers'] for promotion in promotions_layer_2])

    if len(promotions) == 0:
        return None

    return EpicGamesOffer(
        title=d.get('title'),
        description=d.get('description'),
        starts_at=promotions[0]['startDate'],
        ends_at=promotions[0]['endDate'],
        page_slug=d.get('offerMappings')[0].get('pageSlug'),
        image_tall_url=image_urls.get('OfferImageTall'),
        image_thumbnail_url=image_urls.get('Thumbnail'),
    )





import asyncio
import io
import logging
from datetime import datetime
from typing import Tuple, List, Optional

from PIL import Image
from aiohttp import ClientResponseError
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import CallbackContext

from bobweb.bob import async_http, database
from bobweb.bob.broadcaster import broadcast_to_chats
from bobweb.bob.command import ChatCommand, regex_simple_command
from bobweb.bob.command_image_generation import image_to_byte_array
from bobweb.bob.resources.bob_constants import utctz
from bobweb.bob.utils_common import fitzstr_from, has, flatten, object_search, send_bot_is_typing_status_update, \
    strptime_or_none, utctz_from, find_first_not_none

logger = logging.getLogger(__name__)


class EpicGamesOffersCommand(ChatCommand):

    def __init__(self):
        super(EpicGamesOffersCommand, self).__init__(
            name='epicgames',
            regex=regex_simple_command('epicgames'),
            help_text_short=('!epicgames', 'ilmaispelit')
        )

    async def handle_update(self, update: Update, context: CallbackContext = None) -> None:
        await send_bot_is_typing_status_update(update.effective_chat)
        try:
            msg, image_bytes = await find_current_free_game_offers_and_create_message()
            if has(image_bytes):
                await update.effective_message.reply_photo(photo=image_bytes, caption=msg, parse_mode=ParseMode.HTML,
                                                           quote=False)
            else:
                await update.effective_message.reply_text(text=msg, parse_mode=ParseMode.HTML, quote=False)
        except ClientResponseError as e:
            log_msg = f'Epic Games Api error. [status]: {str(e.status)}, [message]: {e.message}, [headers]: {e.headers}'
            logger.exception(log_msg, exc_info=True)
            await update.effective_message.reply_text(fetch_failed_no_connection_msg, quote=False)
        except Exception as e:
            log_msg = f'Epic Games error: {str(e)}'
            logger.exception(log_msg, exc_info=True)
            await update.effective_message.reply_text(fetch_or_processing_failed_msg, quote=False)


fetch_or_processing_failed_msg = 'Ilmaisten eeppisten pelien haku tai tietojen prosessointi epäonnistui 🔌✂️'
fetch_failed_no_connection_msg = 'Ilmaisten eeppisten pelien palveluun ei onnistuttu muodostamaan yhteyttä  🔌✂️'
fetch_ok_no_free_games = 'Uusia ilmaisia eeppisiä pelejä ei ole tällä hetkellä tarjolla 👾'
epic_free_games_api_endpoint = 'https://store-site-backend-static.ak.epicgames.com/freeGamesPromotions?country=FI'
epic_games_store_product_base_url = 'https://store.epicgames.com/en-US/p/'
epic_games_store_free_games_page_url = 'https://store.epicgames.com/en-US/free-games'
epic_games_date_time_format = '%Y-%m-%dT%H:%M:%S.%fZ'


class EpicGamesOffer:
    def __init__(self,
                 title: str,
                 description: str,
                 starts_at: datetime,
                 ends_at: datetime,
                 page_slug: str,
                 image_tall_url: str,
                 image_thumbnail_url: str,
                 image_backup_url: str):
        self.title: str = title
        self.description: str = description
        self.starts_at: datetime = starts_at
        self.ends_at: datetime = ends_at
        self.page_slug: str = page_slug
        self.vertical_img_url: str = image_tall_url
        self.horizontal_img_url: str = image_thumbnail_url
        self.image_backup_url: str = image_backup_url


class NoNewFreeGamesError(Exception):
    """ Simple error class for situation where new games are expected and no new games are found """
    pass


async def daily_announce_new_free_epic_games_store_games(context: CallbackContext):
    """ Tries to find and announce all new game offers starting on current date for 5 minutes. Request offers from Epic
        Games Api once a minute. If no new games are found after 5 minutes no announcement is made. If all requests fail
        and no successful response is gotten, announces failure after 5 minutes is up. Returns immediately after
        successful delivery. This is done to ensure that the bot announces new game offers as soon as possible. """
    chats_with_announcement_on = [x for x in database.get_chats() if x.free_game_offers_enabled]
    if len(chats_with_announcement_on) == 0:
        return  # Early return if no chats with setting turned on

    max_try_count = 5
    try_count = 0
    delay_seconds = 60

    # Possible status'
    client_response_error = None
    response_ok_no_new_games = False

    while try_count < max_try_count:
        # Define either announcement message and possible game images or fetch_failed_msg without image
        try_count += 1
        try:
            msg, image_bytes = await find_new_free_game_offers_and_create_message()
            await broadcast_to_chats(context.bot, chats_with_announcement_on, msg, image_bytes,
                                     parse_mode=ParseMode.HTML)
            return  # Early return after successful announcement
        except ClientResponseError as e:
            # Set client_response_error. If no successful request is done with time period,
            # connection error message is sent
            client_response_error = e
        except NoNewFreeGamesError:
            # If no new games are found. As this means successful request with response,
            # client_response_error is overriden
            client_response_error = None
            response_ok_no_new_games = True
        except Exception as e:
            log_msg = f'Epic Games error: {str(e)}'
            logger.exception(log_msg, exc_info=True)
            await broadcast_to_chats(context.bot, chats_with_announcement_on, fetch_or_processing_failed_msg)
            return  # Most likely not going to be fixed with trying again. So no retries for other exceptions
        finally:
            if try_count < max_try_count:
                await asyncio.sleep(delay_seconds)

    if client_response_error is not None:
        log_msg = (f'Epic Games Api error. [status]: {str(client_response_error.status)}, [message]: '
                   f'{client_response_error.message}, [headers]: {client_response_error.headers}')
        logger.exception(log_msg, exc_info=True)
        await broadcast_to_chats(context.bot, chats_with_announcement_on, fetch_failed_no_connection_msg)

    elif response_ok_no_new_games:
        logger.info('Epic games offers status fetched successfully but no new free games found')
        is_thursday = datetime.today().weekday() == 3  # Monday == 0 ... Sunday == 6
        if is_thursday:
            # Only if it's thursday, should there be announcement that no games were found.
            # On other week days it is the expected outcome
            await broadcast_to_chats(context.bot, chats_with_announcement_on, fetch_ok_no_free_games)


async def find_new_free_game_offers_and_create_message() -> tuple[str, bytes | None]:
    """ Finds all new free game offers starting today. If none is found, or fetch fails, raises an exception """
    games: list[EpicGamesOffer] = await fetch_free_epic_games_offering(only_offers_starting_today=True)
    if len(games) == 0:
        raise NoNewFreeGamesError()

    return await create_message_and_game_image_compilation(games, '📬 Uudet ilmaiset eeppiset pelit 📩')


async def find_current_free_game_offers_and_create_message() -> tuple[str, bytes | None]:
    """ Creates message with current free game offers """
    games: list[EpicGamesOffer] = await fetch_free_epic_games_offering()
    if len(games) == 0:
        return fetch_ok_no_free_games, None

    return await create_message_and_game_image_compilation(games, '📬 Ilmaiset eeppiset pelit 📩')


async def create_message_and_game_image_compilation(games: List[EpicGamesOffer], heading: str) \
        -> Tuple[str, Optional[bytes]]:
    msg = heading + format_games_offer_list(games)
    msg_image = await get_game_offers_image(games)
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


async def fetch_free_epic_games_offering(only_offers_starting_today: bool = False) -> list[EpicGamesOffer]:
    today: datetime.date = datetime.today().date()
    content: dict = await async_http.fetch_json(epic_free_games_api_endpoint)
    # use None-safe dict-get-chain that returns list if any key is not found
    game_dict_list = object_search(content, 'data', 'Catalog', 'searchStore', 'elements') or []

    game_offers = []
    for d in game_dict_list:
        game_offer: EpicGamesOffer = extract_free_game_offer_from_game_dict(d)
        # is added to the list if:
        # - has promotion
        # - only_offers_starting_today is false or if it is set to be true and promotion starts on current day
        if game_offer is not None and (only_offers_starting_today is False or game_offer.starts_at.date() == today):
            game_offers.append(game_offer)

    return game_offers


async def get_game_offers_image(games: list[EpicGamesOffer]) -> Image:
    # Get vertical image for each
    urls = create_list_of_offer_image_urls(games)
    fetched_bytes: Tuple[bytes] = await async_http.fetch_all_content_bytes(urls)
    images: List[Image] = [Image.open(io.BytesIO(b)) for b in fetched_bytes]
    return create_image_collage(images)


def create_list_of_offer_image_urls(games: list[EpicGamesOffer]) -> List[str]:
    urls = []
    has_multiple_games = len(games) > 1
    for game in games:
        # Use first available image based on their priority.
        # 1. Vertical image (if there are multiple games)
        # 2. Horizontal image (if there is a single game)
        # 4. Use possible backup image which type is unknown
        # 5. No image for game
        if has_multiple_games:
            url = find_first_not_none([game.vertical_img_url, game.horizontal_img_url, game.image_backup_url])
        else:
            url = find_first_not_none([game.horizontal_img_url, game.vertical_img_url, game.image_backup_url])

        if has(url):
            urls.append(url)
    return urls


def get_product_page_or_deals_page_url(page_slug: str):
    if has(page_slug):
        return epic_games_store_product_base_url + page_slug
    else:
        return epic_games_store_free_games_page_url


def create_image_collage(images: list[Image.Image]) -> Optional[Image.Image]:
    if len(images) == 0:
        return None

    collage_width = sum([x.width for x in images])
    collage_height = min([x.height for x in images])

    canvas = Image.new('RGB', (collage_width, collage_height))
    next_x_coordinate = 0
    for i, image in enumerate(images):
        canvas.paste(image, (next_x_coordinate, 0))
        next_x_coordinate += image.width
    return canvas


def extract_free_game_offer_from_game_dict(d: dict) -> EpicGamesOffer | None:
    # To get all promotions, concatenate active promotionalOffers with upcomingPromotional offers
    # Example result json in 'bobweb/bob/resources/test/epicGamesFreeGamesPromotionsExample.json'

    current_promotions: list = object_search(d, 'promotions', 'promotionalOffers') or []
    promotional_offers = [promotion['promotionalOffers'] for promotion in current_promotions]
    items_promotions = flatten(promotional_offers)

    is_free = object_search(d, 'price', 'totalPrice', 'discountPrice') == 0

    # Find first active promotion that has start and end time defined
    active_promotion = find_first_active_promotion(items_promotions)
    if active_promotion is None or not is_free:
        return None

    key_images = d.get('keyImages', [])
    image_urls = {}
    for img_obj in key_images:
        image_urls[img_obj['type']] = img_obj['url']

    return EpicGamesOffer(
        title=d.get('title'),
        description=d.get('description'),
        starts_at=strptime_or_none(active_promotion['startDate'], epic_games_date_time_format),
        ends_at=strptime_or_none(active_promotion['endDate'], epic_games_date_time_format),
        page_slug=find_page_slug(d),
        image_tall_url=image_urls.get('OfferImageTall'),
        image_thumbnail_url=image_urls.get('Thumbnail'),
        # In case of key images not having any image with expected types,
        # use the first one if it exists
        image_backup_url=object_search(key_images, 0, 'url') if len(key_images) > 0 else None
    )


def find_first_active_promotion(promotions: list) -> Optional[dict]:
    # Now iterate through all the promotions and find first that is active currently
    now = datetime.now(utctz)
    for promotion in promotions:
        start_dt = strptime_or_none(promotion['startDate'], epic_games_date_time_format)
        end_dt = strptime_or_none(promotion['endDate'], epic_games_date_time_format)

        if (start_dt and end_dt) and utctz_from(start_dt) <= now < utctz_from(end_dt):
            return promotion
    # If no promotion had both start and end date or was not active at the moment, non is returned
    return None


def find_page_slug(data: dict):
    # try all known paths and return first non-None result
    return object_search(data, 'catalogNs', 'mappings', 0, 'pageSlug') \
           or object_search(data, 'offerMappings', 0, 'pageSlug')






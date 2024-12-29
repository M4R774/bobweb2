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

from bobweb.bob import main, async_http, database
from bobweb.bob.broadcaster import broadcast_to_chats
from bobweb.bob.command import ChatCommand, regex_simple_command
from bobweb.bob.command_image_generation import image_to_byte_array
from bobweb.bob.message_board import MessageWithPreview
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
            msg, image_bytes = await find_game_offers_and_create_message(only_offers_starting_today=False,
                                                                         fetch_images=True)
            if has(image_bytes):
                await update.effective_chat.send_photo(photo=image_bytes, caption=msg, parse_mode=ParseMode.HTML)
            else:
                await update.effective_chat.send_message(text=msg, parse_mode=ParseMode.HTML)
        except NoNewFreeGamesError:
            # Expected when no new games are available
            await update.effective_chat.send_message(fetch_ok_no_free_games)
        except ClientResponseError as e:
            log_msg = f'Epic Games Api error. [status]: {str(e.status)}, [message]: {e.message}, [headers]: {e.headers}'
            logger.exception(log_msg, exc_info=True)
            await update.effective_chat.send_message(fetch_failed_no_connection_msg)
        except Exception as e:
            log_msg = f'Epic Games error: {str(e)}'
            logger.exception(log_msg, exc_info=True)
            await update.effective_chat.send_message(fetch_or_processing_failed_msg)


fetch_or_processing_failed_msg = 'Ilmaisten eeppisten pelien haku tai tietojen prosessointi epäonnistui 🔌✂️'
fetch_failed_no_connection_msg = 'Ilmaisten eeppisten pelien palveluun ei onnistuttu muodostamaan yhteyttä  🔌✂️'
fetch_ok_no_free_games = 'Uusia ilmaisia eeppisiä pelejä ei ole tällä hetkellä tarjolla 👾'
epic_free_games_api_endpoint = 'https://store-site-backend-static.ak.epicgames.com/freeGamesPromotions?country=FI'
epic_games_store_product_base_url = 'https://store.epicgames.com/en-US/p/'
epic_games_store_free_games_page_url = 'https://store.epicgames.com/en-US/free-games'
epic_games_date_time_format = '%Y-%m-%dT%H:%M:%S.%fZ'
ending_game_offers_heading = "Vielä ehdit 🚨 Päättyvät tarjoukset ⚠️"
failed_fetch_wait_delay_before_retry = 60


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
    chats_with_announcement_on: List[int] = [chat.id for chat in database.get_chats() if chat.free_game_offers_enabled]
    if len(chats_with_announcement_on) == 0:
        return  # Early return if no chats with setting turned on

    _, msg, image_bytes = await find_free_games_or_return_error_msg()
    if msg:
        await broadcast_to_chats(context.bot, chats_with_announcement_on, msg, image_bytes,
                                 parse_mode=ParseMode.HTML)


async def find_free_games_or_return_error_msg(only_offers_starting_today: bool = True,
                                              fetch_images: bool = True,
                                              message_heading: str = None) \
        -> Tuple[bool, Optional[str], Optional[bytes]]:
    """ Tries to find and announce all new game offers for 5 minutes. Returns tuple:
        - bool: true if games were found, false if failed and retries were exhausted or no games found
        - Optional[str]: message content with free game offer details
        - Optional[bytes]: message image byte content
    """
    max_try_count = 5
    try_count = 0

    # Possible status'
    client_response_error: ClientResponseError | None = None
    response_ok_no_new_games: bool = False

    while try_count < max_try_count:
        # Define either announcement message and possible game images or fetch_failed_msg without image
        try_count += 1
        try:
            # Return after successful announcement
            message, image = await find_game_offers_and_create_message(
                only_offers_starting_today=only_offers_starting_today,
                fetch_images=fetch_images,
                message_heading=message_heading)
            return True, message, image
        except ClientResponseError as e:
            # Set client_response_error. If no successful request is done with time period,
            # connection error message is sent
            client_response_error = e
        except NoNewFreeGamesError:
            # If no new games are found. As this means successful request with response,
            # client_response_error is overridden. New offers might not be yet available in
            # the api, so the call is retried and only after max_try_count is reached are
            # users notified based on the current week day.
            client_response_error = None
            response_ok_no_new_games = True
        except Exception as e:
            log_msg = f'Epic Games error: {str(e)}'
            logger.exception(log_msg, exc_info=True)
            # Most likely not going to be fixed with trying again. So no retries for other exceptions
            return False, fetch_or_processing_failed_msg, None

        if try_count < max_try_count:
            await asyncio.sleep(failed_fetch_wait_delay_before_retry)

    if client_response_error is not None:
        log_msg = (f'Epic Games Api error. [status]: {str(client_response_error.status)}, [message]: '
                   f'{client_response_error.message}, [headers]: {client_response_error.headers}')
        logger.exception(log_msg, exc_info=True)
        return False, fetch_failed_no_connection_msg, None
    elif response_ok_no_new_games:
        logger.info('Epic games offers status fetched successfully but no new free games found')
        is_thursday = datetime.today().weekday() == 3  # Monday == 0 ... Sunday == 6
        if is_thursday:
            # Only if it's thursday, should there be announcement that no games were found.
            # On other week days it is the expected outcome
            return False, fetch_ok_no_free_games, None
    return False, None, None


async def create_message_board_message(message_heading: str = None) -> MessageWithPreview | None:
    """ Finds current Epic games offering and creates message for the message board. As message board does not contain
        any images, only the text content is added to the message board message.
        If no free games found, returns None. This way, the board is not updated. """
    game_offers_found, msg, _ = await find_free_games_or_return_error_msg(only_offers_starting_today=False,
                                                                          fetch_images=False,
                                                                          message_heading=message_heading)
    if game_offers_found and msg:
        return MessageWithPreview(msg, None, ParseMode.HTML)
    else:
        return None


async def create_message_board_message_for_ending_offers() -> MessageWithPreview | None:
    """ Create message board messages for ending free game offers """
    return await create_message_board_message(message_heading=ending_game_offers_heading)


async def find_game_offers_and_create_message(only_offers_starting_today: bool,
                                              fetch_images: bool = True,
                                              message_heading: str = None) -> tuple[str, bytes | None]:
    """ Finds game offers. If none is found, or fetch fails, raises an exception.
        If only_offers_starting_today is True returns only offers that have their offer period starting date today.
        If fetch_images is True, returns image collage for the offers."""
    games: list[EpicGamesOffer] = await fetch_free_epic_games_offering(only_offers_starting_today)
    if len(games) == 0:
        raise NoNewFreeGamesError()

    if message_heading:
        heading = message_heading
    elif only_offers_starting_today:
        heading = '📬 Uudet ilmaiset eeppiset pelit 📩'
    else:
        heading = '📬 Ilmaiset eeppiset pelit 📩'
    return await create_message_and_game_image_compilation(games, heading, fetch_images=fetch_images)


async def create_message_and_game_image_compilation(games: List[EpicGamesOffer],
                                                    heading: str,
                                                    fetch_images: bool) -> Tuple[str, Optional[bytes]]:
    msg = heading + format_games_offer_list(games)
    msg_image = await get_game_offers_image(games) if fetch_images else None
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
    content: dict = await async_http.get_json(epic_free_games_api_endpoint)
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
    fetched_bytes: Tuple[bytes] = await async_http.get_all_content_bytes_concurrently(urls)
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

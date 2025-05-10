import asyncio
import base64
import io
import logging
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, Optional, List

import telethon
from telegram import Message as PtbMessage, User as PtbUser, Chat as PtbChat, Update as PtbUpdate
from telethon import TelegramClient
from telethon.hints import Entity, TotalList

import bobweb
from bobweb.bob import config, openai_api_utils
from telethon.tl.types import Message as TelethonMessage, Chat as TelethonChat, User as TelethonUser

from bobweb.bob.utils_common import ChatMessage, ContentOrigin

logger = logging.getLogger(__name__)


#
# Note! This module contains modules from both Python Telegram Bot API and Telethon Telegram Client API. Class names
# has been renamed with alias to reflect which APIs class is used in the context.
#


def are_telegram_client_env_variables_set() -> bool:
    if not config.tg_client_api_id or not config.tg_client_api_hash:
        logger.warning("Telegram client api ID and api Hash environment variables are missing. Can not start Telethon "
                       "Telegram Client alongside Python Telegram Bot application. However bot can still be run "
                       "without Telegram client api. This affects some functionalities (GPT-command not being able to "
                       "fetch all messages in reply chains).")
        return False
    return True


class TelethonEntityCacheItem:
    """ Simple class that hold reference to Telethon entity item and datetime when cached.
        Telethon entity can be a chat, a user or a channel """

    def __init__(self, entity: Entity):
        self.cached_at: datetime = datetime.now()
        self.entity: Entity = entity


class TelethonClientWrapper:
    """ Class that holds single reference to client object """

    # How long item can be used from cache before refresh
    _cache_refresh_limit_hours = 6

    def __init__(self) -> None:
        self._client: TelegramClient | None = None
        self.chat_ref_cache: Dict[int, TelethonEntityCacheItem] = {}
        self.user_ref_cache: Dict[int, TelethonEntityCacheItem] = {}

    def is_initialized(self):
        """ Non Async function to check if client has / will be initialized """
        return self._client is not None

    async def initialize_and_get_telethon_client(self):
        """ Lazy evaluation singleton. If not yet initiated, creates new. Otherwise, returns existing """
        if self._client is None:
            if not are_telegram_client_env_variables_set():
                raise ValueError("Telegram client api ID and api Hash environment variables are missing")
            self._client: telethon.TelegramClient = telethon.TelegramClient('bot', int(config.tg_client_api_id),
                                                                            config.tg_client_api_hash)
        if self._client.is_connected() is False:
            await self._connect()
        return self._client

    async def _connect(self):
        """ Connects Telethon Telegram client if required environment variables are set. This is not required, as only
            some functionalities require full telegram client connection. For easier development, bot can be run without
            any Telegram client env-variables """
        if self._client is None:
            raise ValueError("No Client initialized, cannot connect.")

        await self._client.start(bot_token=config.bot_token)
        await self._client.connect()

        me = await self._client.get_me()
        logger.info(f"Connected to Telegram client with user={me.username}")
        return self._client

    def close(self):
        """ Closes telegram client connection if needed"""
        if self._client is not None and self._client.is_connected():
            asyncio.run(self._client.disconnect())

    async def find_message(self, chat_id: int, msg_id) -> Optional[PtbMessage]:
        """ Finds message with given id from chat with given id """
        chat: PtbChat = await self.find_chat(chat_id)
        if chat:
            result: TotalList = await self._client.get_messages(chat, ids=[msg_id])
            return result[0] if result else None
        return None

    async def find_user(self, user_id: int) -> Optional[PtbUser]:
        """ Finds user with given id. Returns None if it does not exist or is
            not known to logged-in user. Uses cache. """
        return await self._find_entity(client.user_ref_cache, user_id)

    async def find_chat(self, chat_id: int) -> Optional[PtbChat]:
        """ Finds chat with given id. Returns None if it does not exist or is
            not known to logged-in user. Uses cache. """
        return await self._find_entity(client.chat_ref_cache, chat_id)

    async def _find_entity(self, cache: Dict[int, TelethonEntityCacheItem], entity_id: int) -> Optional[Entity]:
        """ Returns entity with given id with currently authorized login permissions. Returns None, if given entity
            does not exist or currently logged in entity has no relation with entity with given id."""
        invalidate_all_cache_items_that_cache_time_limit_has_exceeded(cache, self._cache_refresh_limit_hours)

        cache_item = cache.get(entity_id)
        if cache_item is not None:
            # item is cached and its timelimit is not yet met => return it
            return cache_item.entity
        else:
            # find entity from telegram api and cache it if not none and return
            entity: Entity = await self._client.get_entity(entity_id)
            if entity is not None:
                cache[entity_id] = TelethonEntityCacheItem(entity=entity)
            return entity

    async def download_all_messages_image_bytes(self, messages: List[PtbMessage]) -> List[io.BytesIO]:
        bytes_list: List[io.BytesIO] = []
        for message in messages:
            downloaded_bytes = await self.download_message_image_bytes(message)
            bytes_list.append(downloaded_bytes)
        return bytes_list

    async def download_message_image_bytes(self, message: PtbMessage) -> io.BytesIO:
        return await self._client.download_media(message.media.photo, file=io.BytesIO())

    async def get_all_messages_in_same_media_group(self, chat, original_message, search_id_limit=10) -> List[PtbMessage]:
        """
        Problem: When user sends multiple images in one message, each image is its own message in telegram.
        However, the chat client renders those images to be within the same message or gallery. When multiple
        images are sent at the same time, Telegram assigns those images same 'media_group_id'
        ("grouped_id" in Telethons API). That is the only way to combine those images together and find all images
        associated with the original message.

        Searches for Telegram messages that have same media_group_id associated with original_message.
        As telegram bot might receive message with media in different order than they are created, the message with
        the caption text might not be the first message received by the bot and or other items in the group might have
        smaller sequential message id. So this searches messages with ids in range
        [original_message.id - search_id_limit, original_message.id + search_id_limit + 1] to find all images for the
        group.
        Returns a list of [media] where each post has media and is in the same grouped_id.

        More info: https://core.telegram.org/api/files#albums-grouped-media
        """
        if original_message is None or original_message.media is None:
            return []  # No message or media
        if original_message.grouped_id is None:
            return [original_message]  # Media has no group id, so it is a singular message with media

        range_start, range_end = original_message.id - search_id_limit, original_message.id + search_id_limit + 1
        search_ids = [i for i in range(range_start, range_end)]
        messages = await self._client.get_messages(chat, ids=search_ids)
        all_found_messages_in_group = []
        for message in messages:
            if message is not None and message.grouped_id == original_message.grouped_id and message.media is not None:
                all_found_messages_in_group.append(message)
        return all_found_messages_in_group


def invalidate_all_cache_items_that_cache_time_limit_has_exceeded(cache: Dict[int, TelethonEntityCacheItem],
                                                                  time_limit_hours: int):
    """ Invalidates all cache items that have expired """
    cache_time_limit = datetime.now() - timedelta(hours=time_limit_hours)
    for entity_id, cache_item in cache.copy().items():
        if cache_item.cached_at < cache_time_limit:
            cache.pop(entity_id)


async def form_message_history(update: PtbUpdate) -> List[ChatMessage]:
    """ Forms message history for reply chain. Latest message is last in the result list.
        Meaning the messages are in the chronological order from the oldest to the newest.
        This method uses both PTB (Telegram bot api) and Telethon (Telegram client api).
        Adds all images contained in any messages in the reply chain to the message history """
    messages: list[ChatMessage] = []

    # First create object of current message
    cleaned_message = bobweb.bob.openai_api_utils.remove_openai_related_command_text_and_extra_info(
        update.effective_message.text)

    # If message has image, download all possible images related to the message by media_group_id
    # (Each image is its own message even though they appear to be grouped in the chat client)
    base_64_images = []
    if update.effective_message.photo:
        base_64_images = await download_all_images_as_base_64_strings_for_update(update)

    if cleaned_message != '' or len(base_64_images) > 0:
        # If the message contained only gpt-command, it is not added to the history
        messages.append(ChatMessage(ContentOrigin.USER, cleaned_message, base_64_images))

    # If current message is not a reply to any other, early return with it
    reply_to_msg = update.effective_message.reply_to_message
    if reply_to_msg is None:
        return messages

    # Now, current message is reply to another message that might be replied to another.
    # Iterate through the reply chain and find all messages in it
    next_id = reply_to_msg.message_id

    # Iterate over all messages in the reply chain. Telethon Telegram Client is used from here on
    while next_id is not None:
        message, next_id = await find_and_add_previous_message_in_reply_chain(update.effective_chat.id, next_id)
        if message is not None:
            messages.append(message)

    messages.reverse()
    return messages


async def find_and_add_previous_message_in_reply_chain(chat_id: int, next_id: int) -> \
        tuple[Optional[ChatMessage], Optional[int]]:
    # Telethon api from here on. Find message with given id. If it was a reply to another message,
    # fetch that and repeat until no more messages are found in the reply thread

    current_message: TelethonMessage = await client.find_message(chat_id=chat_id, msg_id=next_id)
    # Message authors id might be in attribute 'peer_id' or in 'from_id'
    author_id = None
    if current_message.from_id and current_message.from_id.user_id:
        author_id = current_message.from_id.user_id

    if author_id is None:
        # If author is not found, set message to be from user
        is_bot = False
    else:
        author: TelethonUser = await client.find_user(author_id)  # Telethon User
        is_bot = author.bot

    next_id = current_message.reply_to.reply_to_msg_id if current_message.reply_to else None

    base_64_images = []
    if current_message.media and hasattr(current_message.media, 'photo') and current_message.media.photo:
        chat = await client.find_chat(chat_id)
        base_64_images = await download_all_images_as_base_64_strings(chat, current_message)

    cleaned_message = openai_api_utils.remove_openai_related_command_text_and_extra_info(current_message.message)
    if cleaned_message != '' or len(base_64_images) > 0:
        # If author of message is bot, it's message is added with role assistant and
        # cost so far notification is removed from its messages
        context_role = ContentOrigin.BOT if is_bot else ContentOrigin.USER
        message = ChatMessage(context_role, cleaned_message, base_64_images)
        return message, next_id

    return None, next_id


async def download_all_images_as_base_64_strings_for_update(update: PtbUpdate) -> List[str]:
    # Handle any possible media. Message might contain a single photo or might be a part of media group that contains
    # multiple photos. All images in media group can't be requested in any straightforward way. Here we try to find
    # All associated photos and add them to the message history. This search uses Telethon Client API.
    chat = await client.find_chat(update.effective_chat.id)
    original_message = await client.find_message(chat.id, update.effective_message.message_id)
    return await download_all_images_as_base_64_strings(chat, original_message)


async def download_all_images_as_base_64_strings(chat: TelethonChat, message: TelethonMessage) -> List[str]:
    messages = await client.get_all_messages_in_same_media_group(chat, message)
    image_bytes_list = await client.download_all_messages_image_bytes(messages)
    return convert_all_image_bytes_base_64_data(image_bytes_list)


def convert_all_image_bytes_base_64_data(image_bytes_list: List[io.BytesIO]) -> List[str]:
    """ Converts all io.BytesIO objects to base64 data strings """
    base_64_images = []
    for image_bytes in image_bytes_list:
        base64_photo = base64.b64encode(image_bytes.getvalue()).decode('utf-8')
        image_url = f'data:image/jpeg;base64,{base64_photo}'
        base_64_images.append(image_url)
    return base_64_images


# Singleton instance of the Telethon telegram client wrapper object
client = TelethonClientWrapper()

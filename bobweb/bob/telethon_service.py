import asyncio
import io
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional, List

import telethon
from telethon import TelegramClient
from telethon.hints import Entity, TotalList

from bobweb.bob import config

from telethon.tl.types import Chat, User, Message, Photo

logger = logging.getLogger(__name__)


def are_telegram_client_env_variables_set() -> bool:
    if config.api_id is None or config.api_hash is None:
        logger.warning("Telegram client api ID and api Hash environment variables are missing. Can not start Telethon "
                       "Telegram Client alongside Python Telegram Bot application. However bot can still be run "
                       "without Telegram client api")
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
            self._client: telethon.TelegramClient = telethon.TelegramClient('bot', int(config.api_id), config.api_hash)
        if self._client.is_connected() is False:
            await self.__connect()
        return self._client

    async def __connect(self):
        """ Connects Telethon Telegram client if required environment variables are set. This is not required, as only
            some functionalities require full telegram client connection. For easier development, bot can be run without
            any Telegram client env-variables """
        if self._client is None:
            return None

        await self._client.start(bot_token=config.bot_token)
        await self._client.connect()

        me = await self._client.get_me()
        logger.info(f"Connected to Telegram client with user={me.username}")
        return self._client

    def close(self):
        """ Closes telegram client connection if needed"""
        if self._client is not None and self._client.is_connected():
            asyncio.run(self._client.disconnect())

    async def find_message(self, chat_id: int, msg_id) -> Optional[Message]:
        """ Finds message with given id from chat with given id """
        chat: Chat = await self.find_chat(chat_id)
        if chat is None:
            return None
        result: TotalList = await self._client.get_messages(chat, ids=[msg_id])
        if len(result) == 0:
            return None
        else:
            return result[0]

    async def find_user(self, user_id: int) -> Optional[User]:
        """ Finds user with given id. Retuns None if it does not exist or is
            not known to logged-in user. Uses cache. """
        return await self._find_entity(client.user_ref_cache, user_id)

    async def find_chat(self, chat_id: int) -> Optional[Chat]:
        """ Finds chat with given id. Retuns None if it does not exist or is
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

    async def download_message_image_bytes(self, message: Message) -> bytes:
        return await self._client.download_media(message.media.photo, file=io.BytesIO())

    async def download_all_messages_image_bytes(self, messages: List[Message]) -> List[bytes]:
        bytes_list: List[bytes] = []
        for message in messages:
            downloaded_bytes = await self.download_message_image_bytes(message)
            bytes_list.append(downloaded_bytes)
        return bytes_list

    async def get_all_messages_in_same_media_group(self, chat, original_message, search_id_limit=10) -> List[Message]:
        """
        Searches for Telegram messages that have same media_group_id associated with original_post.
        As telegram bot might receive message with media in different order than they are created,
        the grouped items might have smaller id as the one received by the bot.
        Returns a list of [media] where each post has media and is in the same grouped_id
        """
        if original_message.grouped_id is None:
            return [original_message] if original_message.media is not None else []

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


# Singleton instance of the Telethon telegram client wrapper object
client = TelethonClientWrapper()






import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional

from telethon import TelegramClient
from telethon.hints import Entity, TotalList

from bobweb.bob.config import api_hash, api_id, bot_token

from telethon.tl.types import Chat, User, Message

logger = logging.getLogger(__name__)


def init_telegram_client() -> TelegramClient | None:
    """ Returns initiated Telegram client or None """
    if api_id is None or api_hash is None:
        logger.warning("Telegram client api ID and api Hash environment variables are missing. Can not start Telethon "
                       "Telegram Client alongside Python Telegram Bot application. However bot can still be run "
                       "without Telegram client api")
        return None
    else:
        return TelegramClient('bot', int(api_id), api_hash)


class TelethonEntityCacheItem:
    """ Simple class that hold reference to Telethon entity item and datetime when cached.
        Telethon entity can be a chat, a user or a channel """
    def __init__(self, entity: Entity):
        self.cached_at: datetime = datetime.now()
        self.entity: Entity = entity


class TelegramClientWrapper:
    """ Class that holds single reference to client object """

    # How long item can be used from cache before refresh
    cache_refresh_limit_hours = 6

    def __init__(self) -> None:
        self._client: TelegramClient | None = None
        self.chat_ref_cache: Dict[int, TelethonEntityCacheItem] = {}
        self.user_ref_cache: Dict[int, TelethonEntityCacheItem] = {}

    async def get_client(self):
        """ Lazy evaluation singleton. If not yet initiated, creates new. Otherwise, returns existing """
        if self._client is None:
            self._client: TelegramClient = init_telegram_client()
        if self._client.is_connected() is False:
            await self.__connect()
        return self._client

    async def __connect(self):
        """ Connects Telethon Telegram client if required environment variables are set. This is not required, as only
            some functionalities require full telegram client connection. For easier development, bot can be run without
            any Telegram client env-variables """
        if self._client is None:
            return None

        await self._client.start(bot_token=bot_token)
        await self._client.connect()

        me = await self._client.get_me()
        logger.info(f"Connected to Telegram client with user={me.username}")
        return self._client


# Singleton instance of the Telethon telegram client wrapper object
instance = TelegramClientWrapper()


def has_telegram_client():
    """ Non Async function to check if client has / will be initialized """
    return instance.get_client() is not None  # instance.client returns coroutine, if has client


async def get_client():
    """ Returns lazy-evaluated, lazy-connected client object. """
    return await instance.get_client()


async def find_message(chat_id: int, msg_id) -> Optional[Message]:
    """ Finds message with given id from chat with given id """
    chat: Chat = await find_chat(chat_id)
    if chat is None:
        return None
    client = await get_client()
    result: TotalList = await client.get_messages(chat, ids=[msg_id])
    if len(result) == 0:
        return None
    else:
        return result[0]


async def find_user(user_id: int) -> Optional[User]:
    """ Finds user with given id. Retuns None if it does not exist or is
        not known to logged-in user. Uses cache. """
    return await _find_entity(instance.user_ref_cache, user_id)


async def find_chat(chat_id: int) -> Optional[Chat]:
    """ Finds chat with given id. Retuns None if it does not exist or is
        not known to logged-in user. Uses cache. """
    return await _find_entity(instance.chat_ref_cache, chat_id)


async def _find_entity(cache: Dict[int, TelethonEntityCacheItem], entity_id: int) -> Optional[Entity]:
    """ Returns entity with given id with currently authorized login permissions. Returns None, if given entity does not
        exist or currently logged in entity has no relation with entity with given id."""
    cache_item = cache.get(entity_id)
    cache_time_limit = datetime.now() - timedelta(hours=TelegramClientWrapper.cache_refresh_limit_hours)

    if cache_item is not None and cache_item.cached_at > cache_time_limit:
        # item is cached and its timelimit is not yet met => return it
        return cache_item.entity
    else:
        # find entity from telegram api and cache it if not none and return
        client = await get_client()
        entity: Entity = await client.get_entity(entity_id)
        if entity is not None:
            cache[entity_id] = TelethonEntityCacheItem(entity=entity)
        return entity


def close():
    """ Closes telegram client connection if needed"""
    client = asyncio.run(get_client())
    if instance.get_client() is not None and client.is_connected():
        asyncio.run(client.disconnect())

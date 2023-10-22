import asyncio
import logging

from telethon import TelegramClient
from bobweb.bob.config import api_hash, api_id, bot_token

logger = logging.getLogger(__name__)


def init_telegram_client() -> TelegramClient | None:
    """ Returns initiated Telegram client or None """
    if api_id is None or api_hash is None:
        logger.warning("Telegram client api ID and api Hash environment variables are missing. Can not start Telethon "
                       "Telegram Client alongside Python Telegram Bot application. However bot can still be run "
                       "without Telegram client api")
        return None
    else:
        return TelegramClient('anon', int(api_id), api_hash)


class TelegramClientWrapper:
    """ Class that holds single reference to client object """

    def __init__(self) -> None:
        self._client: TelegramClient | None = None

    @property
    async def client(self):
        """ Lazy evaluation singleton. If not yet initiated, creates new. Otherwise, returns existing """
        if self._client is None:
            self._client: TelegramClient = init_telegram_client()
        if self._client.is_connected() is False:
            await self.__connect()
        return self._client

    @client.setter
    def client(self, _):
        """ Raises an error if value is tried to set """
        raise ValueError("This value should not be set")

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
    return instance.client is not None  # instance.client returns coroutine, if has client


async def get_client():
    """ Returns lazy-evaluated, lazy-connected client object. """
    return await instance.client


def close():
    """ Closes telegram client connection if needed"""
    client = asyncio.run(get_client())
    if instance.client is not None and client.is_connected():
        asyncio.run(client.disconnect())

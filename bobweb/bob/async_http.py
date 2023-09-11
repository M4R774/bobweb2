import asyncio
from typing import List, Tuple

import aiohttp
from aiohttp import ClientSession


class HttpClient:
    """ Class that holds single reference to session object shared by all http requests """
    def __init__(self) -> None:
        self.session = None

    def create_session(self):
        if self.session is None:
            self.session: ClientSession = aiohttp.ClientSession()
        return self

    async def close(self):
        if self.session is not None:
            await self.close()


# Singleton instance of the HttpClient object
client = HttpClient()


async def fetch_json(url: str) -> dict:
    """ Makes asynchronous http get request, fetches content and parses it as json.
        Raises ClientResponseError if status not 200 OK.  """
    async with client.session.get(url) as res:
        res.raise_for_status()
        return await res.json()


async def fetch_all_content_bytes(urls: List[str]) -> Tuple[bytes]:
    """ Fetches multiple requests concurrently and return byte contents as tuple with same
        order as given url list. Raises ClientResponseError, if any get request returns
        with status code != 200 OK """
    tasks = [fetch_content_bytes(url) for url in urls]
    return await asyncio.gather(*tasks)


async def fetch_content_bytes(url: str):
    """ Fetches single get request to url and returns payloads byte content.
        Raises ClientResponseError if response status is != 200 OK """
    async with client.session.get(url) as res:
        res.raise_for_status()
        return await res.content.read()

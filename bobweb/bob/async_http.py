import asyncio
from typing import List, Tuple

import aiohttp
from aiohttp import ClientSession, ClientResponse


class HttpClient:
    """ Class that holds single reference to session object shared by all aiohttp requests """

    def __init__(self) -> None:
        self._session = None

    @property
    def session(self):
        """ Lazy evaluation singleton. If not yet initiated, creates new. Otherwise, returns existing """
        if self._session is None:
            self._session: ClientSession = aiohttp.ClientSession()
        return self._session

    @session.setter
    def session(self, _):
        """ Only closes session if value is tried to set """
        self.close()

    def close(self):
        if self._session is not None:
            asyncio.run(self._session.close())


# Singleton instance of the HttpClient object
client = HttpClient()


async def get(url: str,
              headers: dict = None,
              params: dict = None) -> ClientResponse:
    """ Makes asynchronous http get request """
    return await client.session.get(url, headers=headers, params=params)


async def get_json(url: str,
                   headers: dict = None,
                   params: dict = None) -> dict:
    """ Makes asynchronous http get request, fetches content and parses it as json.
        Raises ClientResponseError if status not 200 OK.  """
    async with client.session.get(url, headers=headers, params=params) as res:
        res.raise_for_status()
        return await res.json()


async def get_all_content_bytes_concurrently(urls: List[str],
                                             headers: dict = None,
                                             params: dict = None) -> Tuple[bytes]:
    """ Fetches multiple requests concurrently and return byte contents as tuple with same
        order as given url list. Raises ClientResponseError, if any get request returns
        with status code != 200 OK """
    tasks = [get_content_bytes(url, headers=headers, params=params) for url in urls]
    return await asyncio.gather(*tasks)


async def get_content_bytes(url: str,
                            headers: dict = None,
                            params: dict = None) -> bytes:
    """ Fetches single get request to url and returns payloads byte content.
        Raises ClientResponseError if response status is not 200 OK """
    async with client.session.get(url, headers=headers, params=params) as res:
        res.raise_for_status()
        return await res.content.read()


async def post(url: str,
               data: any = None,
               json: dict = None,
               headers: dict = None,
               params: dict = None) -> ClientResponse:
    """ Makes asynchronous http post request. """
    return await client.session.post(url, headers=headers, params=params, data=data, json=json)


async def post_expect_json(url: str,
                           data: any = None,
                           json: dict = None,
                           headers: dict = None,
                           params: dict = None) -> dict:
    """ Makes asynchronous http post request, fetches response content and parses it as json.
        Raises ClientResponseError if status not 200 OK. """
    async with client.session.post(url, headers=headers, params=params, data=data, json=json) as res:
        res.raise_for_status()
        return await res.json()


async def post_expect_text(url: str,
                           data: any = None,
                           json: dict = None,
                           headers: dict = None,
                           params: dict = None) -> str:
    """ Makes asynchronous http post request, fetches response content and parses it as text.
        Raises ClientResponseError if status not 200 OK. """
    async with client.session.post(url, headers=headers, params=params, data=data, json=json) as res:
        res.raise_for_status()
        return await res.text()


async def post_expect_bytes(url: str,
                            data: any = None,
                            json: dict = None,
                            headers: dict = None,
                            params: dict = None) -> bytes:
    """ Makes asynchronous http post request, fetches response content and returns the bytes.
        Raises ClientResponseError if status not 200 OK. """
    async with client.session.post(url, headers=headers, params=params, data=data, json=json) as res:
        res.raise_for_status()
        return await res.read()

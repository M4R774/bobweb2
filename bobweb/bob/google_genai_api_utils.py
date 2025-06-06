import os
import logging

from google import genai
from aiohttp import ClientResponse

from bobweb.bob import config
from bobweb.bob.openai_api_utils import ResponseGenerationException

logger = logging.getLogger(__name__)


async def handle_google_genai_response_ok_but_missing_content():
    """ Google GenAI has a case where they return 200 but without content. """
    error_response_to_user = "Googlen palvelu ei toimittanut."
    log_level = logging.INFO
    log_message = "Google GenAI API returned 200 but without content."
    logger.log(level=log_level, msg=log_message)
    raise ResponseGenerationException(error_response_to_user)


async def handle_google_genai_response_not_ok(response: ClientResponse,
                                        general_error_response: str):
    """ Common error handler for all Google GenAI API non 200 ok responses.
        API documentation: https://ai.google.dev/gemini-api/docs/troubleshooting#error-codes """
    response_json = await response.json()
    error = response_json[0]['error']
    error_code = error['code']
    error_status = error['status']
    message = error['message']

    # Default values if more exact reason cannot be extracted from response
    error_response_to_user = general_error_response
    log_message = f'Google GenAI API request failed. [error_code]: "{error_code}", [message]:"{message}"'
    log_level = logging.ERROR

    if response.status == 400 and error_status == 'INVALID_ARGUMENT':
        error_response_to_user = 'Virhe keskustelun syöttämisessä Googlelle.'
        log_message = f"Google GenAI API request body is malformed. [error_code]: {error_code} [message]:{message}"
        log_level = logging.ERROR
    elif response.status == 400 and error_status == 'FAILED_PRECONDITION':
        error_response_to_user = 'Virhe maksutiedoissa.'
        log_message = f"Google GenAI API has problem with billing. [error_code]: {error_code} [message]:{message}"
        log_level = logging.ERROR
    elif response.status == 403 and error_status == 'PERMISSION_DENIED':
        error_response_to_user = 'Virhe autentikoitumisessa Googlen järjestelmään.'
        log_message = f"Google GenAI API authentication failed. [error_code]: {error_code} [message]:{message}"
        log_level = logging.ERROR
    elif response.status == 404 and error_status == 'NOT_FOUND':
        error_response_to_user = 'Kysymyksistä tippui media matkalla.'
        log_message = f"Google GenAI API was unable to see linked media. [error_code]: {error_code} [message]:{message}"
        log_level = logging.ERROR
    elif response.status == 429 and error_status == 'RESOURCE_EXHAUSTED':
        error_response_to_user = 'Käytettävissä oleva kiintiö on käytetty.'
        log_message = f"Google GenAI API quota limit reached. [error_code]: {error_code} [message]:{message}"
        log_level = logging.INFO
    elif response.status == 500 and error_status == 'INTERNAL':
        error_response_to_user = ('Googlen palvelussa tapahtui sisäinen virhe.')
        log_message = f"Google GenAI API internal error. [error_code]: {error_code} [message]:{message}"
        log_level = logging.INFO
    elif response.status == 503 and error_status == 'UNAVAILABLE':
        error_response_to_user = ('Googlen palvelu ei ole käytettävissä tai se on juuri nyt ruuhkautunut. '
                                  'Ole hyvä ja yritä hetken päästä uudelleen.')
        log_message = f"Google GenAI API rate limit exceeded. [error_code]: {error_code} [message]:{message}"
        log_level = logging.INFO
    elif response.status == 504 and error_status == 'DEADLINE_EXCEEDED':
        error_response_to_user = ('Googlen mielestä miettiminen kesti liikaa. Kokeile lyhyempää kysymystä.')
        log_message = f"Google GenAI API unable to finish on time. [error_code]: {error_code} [message]:{message}"
        log_level = logging.INFO

    logger.log(level=log_level, msg=log_message)
    raise ResponseGenerationException(error_response_to_user)


def ensure_google_genai_api_key_set():
    """ Checks that google genai api key is set. Raises ValueError if not set to environmental variable. """
    if config.google_genai_api_key is None or config.google_genai_api_key == '':
        logger.error('GOOGLE_GENAI_API_KEY is not set. No response was generated.')
        raise ResponseGenerationException('Google Gen AI API key is missing from environment variables')


class GoogleGenaiApiSession:
    def __init__(self):
        self.default_client = None
    
    def setup_client(self):
        """
        Initializes a client if api key is set as environment variable.
        """
        ensure_google_genai_api_key_set()
        self.default_client = genai.Client(
            api_key=config.google_genai_api_key
        )

    def get_client(self, force_refresh=False):
        """
        Provide already initialized client if one exists.
        If one does not exists or refresh is required, initialize new.
        """
        if self.default_client is None or force_refresh:
            self.setup_client()
        return self.default_client


google_genai_api_session = GoogleGenaiApiSession()

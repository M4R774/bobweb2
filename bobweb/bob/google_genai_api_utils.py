import os
import logging

from google import genai

from bobweb.bob import config
from bobweb.bob.openai_api_utils import ResponseGenerationException

logger = logging.getLogger(__name__)


async def handle_google_gemini_response_ok_but_missing_content():
    """ Google GenAI has a case where they return 200 but without content. """
    error_response_to_user = "Googlen palvelu ei toimittanut."
    log_level = logging.INFO
    log_message = "Google GenAI API returned 200 but without content."
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

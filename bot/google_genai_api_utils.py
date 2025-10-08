import logging

from google import genai

from bot import config
from bot.litellm_utils import ResponseGenerationException

logger = logging.getLogger(__name__)


def ensure_gemini_api_key_set():
    """ Checks that gemini api key is set. Raises ValueError if not set to environmental variable. """
    if config.gemini_api_key is None or config.gemini_api_key == '':
        logger.error('GEMINI_API_KEY is not set. No response was generated.')
        raise ResponseGenerationException('Gemini API key is missing from environment variables')


class GoogleGenaiApiSession:
    def __init__(self):
        self.default_client = None

    def setup_client(self):
        """
        Initializes a client if api key is set as environment variable.
        """
        ensure_gemini_api_key_set()
        self.default_client = genai.Client(
            api_key=config.gemini_api_key
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

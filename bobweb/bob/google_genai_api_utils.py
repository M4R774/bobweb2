import os
import logging

from google import genai

from bobweb.bob.openai_api_utils import ResponseGenerationException

logger = logging.getLogger(__name__)


class GoogleGenaiApiSession:
    def __init__(self):
        self.default_client = None
    
    def setup_client(self):
        """
        Initializes a client if api key is set as environment variable.
        """
        api_key = os.getenv('GOOGLE_GENAI_API_KEY')
        if api_key is None or api_key == '':
            logger.error('GOOGLE_GENAI_API_KEY is not set. No response was generated.')
            raise ResponseGenerationException('Google Gen AI API-avain puuttuu ympäristömuuttujista')
        self.default_client = genai.Client(
            api_key=api_key
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

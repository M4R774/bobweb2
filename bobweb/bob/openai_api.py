import logging
import os

import openai

logger = logging.getLogger(__name__)


def set_openai_api_key():
    """
    Sets OpenAi API-key. Raises ValueError if not set to environmental variable
    """
    api_key_from_env_var = os.getenv('OPENAI_API_KEY')
    if api_key_from_env_var is None or api_key_from_env_var == '':
        raise ValueError('OPENAI_API_KEY is not set.')
    openai.api_key = api_key_from_env_var

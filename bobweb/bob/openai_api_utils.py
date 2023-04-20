import logging
import os

import openai
from telegram import Update

from bobweb.bob import database
from bobweb.web.bobapp.models import TelegramUser

logger = logging.getLogger(__name__)


#
# OpenAi Prices:
#

# ChatGPT price per 1000 tokens
chat_gpt_price_per_1000_tokens = 0.002

# Dalle Image generation prices. Key: resolution, Value: single image price
image_generation_prices = {
    256: 0.016,
    512: 0.018,
    1024: 0.020
}


# Custom Exception for errors caused by image generation
class ResponseGenerationException(Exception):
    def __init__(self, response_text):
        self.response_text = response_text  # Text that is sent back to chat


def ensure_openai_api_key_set():
    """
    Sets OpenAi API-key. Sends message ars reply to update if such is given.
    If not, raises ValueError if not set to environmental variable.

    Raises ResponseGenerationException if key is not set
    """
    api_key_from_env_var = os.getenv('OPENAI_API_KEY')
    if api_key_from_env_var is None or api_key_from_env_var == '':
        logger.error('OPENAI_API_KEY is not set. No response was generated.')
        raise ResponseGenerationException('OpenAI:n API-avain puuttuu ympäristömuuttujista')
    openai.api_key = api_key_from_env_var


def user_has_permission_to_use_openai_api(user_id: int):
    """ Message author has permission to use api if message author is
        credit card holder or message author and credit card holder have a common chat"""
    cc_holder: TelegramUser = database.get_credit_card_holder()
    if cc_holder is None:
        return False

    cc_holder_chat_ids = set(chat.id for chat in cc_holder.chat_set.all())
    author = database.get_telegram_user(user_id)
    author_chat_ids = set(chat.id for chat in author.chat_set.all())

    # Check if there is any overlap in cc_holder_chat_id_list and author_chat_id_list.
    # If so, return True, else return False
    return bool(cc_holder_chat_ids.intersection(author_chat_ids))


def notify_message_author_has_no_permission_to_use_api(update: Update):
    update.effective_message.reply_text('Komennon käyttö on rajattu pienelle testiryhmälle käyttäjiä')


class OpenAiApiState:
    """ Class for OpenAiApi. Keeps track of cumulated costs since last restart """
    def __init__(self):
        self.__cost_so_far = 0

    def add_chat_gpt_cost_get_cost_str(self, total_tokens: int):
        cost = total_tokens * chat_gpt_price_per_1000_tokens / 1000
        self.__cost_so_far += cost
        return self.__get_formatted_cost_str(cost)

    def add_image_cost_get_cost_str(self, n: int, resolution: int):
        """ Dall-e image generation cost is number of generated images
            multiplied with single image price for used resolution """
        cost = n * image_generation_prices[resolution]
        self.__cost_so_far += cost
        return self.__get_formatted_cost_str(cost)

    def get_cost_so_far(self):
        return self.__cost_so_far

    def reset_cost_so_far(self):
        self.__cost_so_far = 0

    def __get_formatted_cost_str(self, cost):
        return 'Rahaa paloi: ${:f}, rahaa palanut rebootin jälkeen: ${:f}'.format(cost, self.__cost_so_far)


state = OpenAiApiState()

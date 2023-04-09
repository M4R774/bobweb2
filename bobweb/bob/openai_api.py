import logging
import os

import openai

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


def set_openai_api_key():
    """
    Sets OpenAi API-key. Raises ValueError if not set to environmental variable
    """
    api_key_from_env_var = os.getenv('OPENAI_API_KEY')
    if api_key_from_env_var is None or api_key_from_env_var == '':
        raise ValueError('OPENAI_API_KEY is not set.')
    openai.api_key = api_key_from_env_var

def user_has_permission_to_use_api():
    """ Mock implementation that returns always true. Proper implementation is done in issue #227 """
    return True


class OpenAiApi:
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

    def __get_formatted_cost_str(self, cost):
        return 'Rahaa paloi: ${:f}, rahaa palanut rebootin jälkeen: ${:f}'.format(cost, self.__cost_so_far)


instance = OpenAiApi()

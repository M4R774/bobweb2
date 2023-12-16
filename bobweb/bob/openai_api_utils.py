import logging
import re
from enum import Enum
from typing import List

import openai
import tiktoken
from telegram import Update
from tiktoken import Encoding

import bobweb
from bobweb.bob import database, config
from bobweb.web.bobapp.models import TelegramUser

logger = logging.getLogger(__name__)


OPENAI_CHAT_COMPLETIONS_API_ENDPOINT = 'https://api.openai.com/v1/chat/completions'


# Dall-e2 Image generation prices. Key: resolution, Value: single image price
image_generation_prices = {
    256: 0.016,
    512: 0.018,
    1024: 0.020
}

# Whisper audio transcribing
whisper_price_per_minute = 0.006


class ContextRole(Enum):
    SYSTEM = 'system'
    ASSISTANT = 'assistant'
    USER = 'user'
    FUNCTION = 'function'


class GptChatMessage:
    """ Single message information in Gpt command message history """
    def __init__(self, role: ContextRole, text: str, base_64_images: List[str] = None):
        self.role = role
        self.text = text
        self.image_urls = base_64_images or []


class GptModel:
    """
    Used GptModels. Value is a tuple of:
    (model, max_tokens, input price, output price)
    Model documentation: https://platform.openai.com/docs/models.
    Prices are per 1000 tokens. More info about pricing: https://openai.com/pricing.
    """
    def __init__(self, name, major_version, has_vision_capabilities, token_limit, input_token_price, output_token_price, message_serializer):
        self.name = name
        self.major_version = major_version
        self.has_vision_capabilities = has_vision_capabilities
        self.token_limit = token_limit
        self.input_token_price = input_token_price
        self.output_token_price = output_token_price
        self.message_serializer = message_serializer

    def serialize_message_history(self, messages: List[GptChatMessage]) -> List[dict]:
        return [self.message_serializer(message) for message in messages]


def msg_serializer_for_text_models(message: GptChatMessage) -> dict[str, str]:
    """ Creates message object for original GPT models without vision capabilities. """
    return {'role': message.role.value, 'content': message.text or ''}


def msg_serializer_for_vision_models(message: GptChatMessage) -> dict[str, str]:
    """ Creates message object for GPT vision model. With vision model, content is a list of objects that can
        be either text messages or images"""
    content = []
    if message.text and message.text != '':
        content.append({'type': 'text', 'text': message.text})

    for image_url in message.image_urls or []:
        if image_url and image_url != '':
            content.append({'type': 'image_url', 'image_url': {'url': image_url}})

    return {'role': message.role.value, 'content': content}


gpt_3_16k = GptModel(
    name='gpt-3.5-turbo-1106',
    major_version=3,
    has_vision_capabilities=False,
    token_limit=16_385,
    input_token_price=0.001,
    output_token_price=0.002,
    message_serializer=msg_serializer_for_text_models
)

gpt_4_128k = GptModel(
    name='gpt-4-1106-preview',
    major_version=4,
    has_vision_capabilities=False,
    token_limit=128_000,
    input_token_price=0.01,
    output_token_price=0.03,
    message_serializer=msg_serializer_for_text_models
)

gpt_4_vision = GptModel(
    name='gpt-4-vision-preview',
    major_version=4,
    has_vision_capabilities=True,
    token_limit=128_000,
    input_token_price=0.01,
    output_token_price=0.03,
    message_serializer=msg_serializer_for_vision_models
)

# All gpt models available for the bot to use. In priority from the lowest major version to the highest.
# Order inside major versions is by vision capability and then by token limit in ascending order.
ALL_GPT_MODELS = [gpt_3_16k, gpt_4_128k, gpt_4_vision]


def find_default_gpt_model_by_version_number(version: str) -> GptModel:
    """ Returns Gpt model for given version string and context_message_list. """
    match version:
        case '3' | '3.5':
            model = gpt_3_16k
        case _:
            model = gpt_4_128k
    return model


def check_context_messages_return_suitable_model(model: GptModel,
                                                 context_message_list: List[GptChatMessage]):
    """
    Checks token count in given message list and appropriate model based on it.
    If context message history contains images and a major model version with
    vision capabilities was requested by the user, returns specific minor
    version with vision capabilities.

    Model context size is calculated from context_message_list using tiktoken
    tokenizer. As models are determined with major-versions and not with a
    strict version number, minor-version updates may have an effect on the
    tokenization. Because of that, 0.5 % or error margin is used so that the
    model context size always fits whole message history if possible.
    """
    # Currently no token count is calculated as the turbo models have low prices with high
    # token limit for each major version.
    # Check if any message in context_message_list contains an image,
    # then switch to vision model
    for message in context_message_list:
        if len(message.image_urls) > 0:
            # Has at least on message with at least one image => Use vision model
            return upgrade_model_to_one_with_vision_capabilities(model, ALL_GPT_MODELS)
    return model


def upgrade_model_to_one_with_vision_capabilities(original_model: GptModel, available_models: List[GptModel]):
    """
    Finds best suited model with vision capabilities and returns it. Priority on choosing model is:
    - Given model, if it has vision
    - Same major version model with vision
    - Nearest greater major version model with vision
    - Nearest lower major version model with vision
    - If there are no models with vision, return the given model
    For example, if user requests response with model X, but the message history contains images:
    - request gpt 3 -> version 3 has no vision model available -> upgrades model to gpt 4 with vision
    - request gpt 4 -> version 4 has vision model available -> upgrades model to gpt 4 with vision
    - request gpt 5 -> version 5 has no vision model available -> downgrades model to gpt 4 with vision
    """
    if original_model.has_vision_capabilities:
        return original_model

    target_major_version = original_model.major_version
    same, greater, lower = None, None, None

    for model in available_models:
        if model.has_vision_capabilities is False:
            continue

        version = model.major_version
        if version == target_major_version:
            same = model
        elif version > target_major_version:
            greater = model
        elif version < target_major_version:
            lower = model

    # Now return first non None model
    suitable_models = [model for model in [same, greater, lower] if model is not None]
    return suitable_models[0] if len(suitable_models) > 0 else original_model


# Custom Exception for errors caused by image generation
class ResponseGenerationException(Exception):
    def __init__(self, response_text):
        self.response_text = response_text  # Text that is sent back to chat


def ensure_openai_api_key_set():
    """
    Sets OpenAi API-key. Sends message as reply to update if such is given.
    If not, raises ValueError if not set to environmental variable.

    Raises ResponseGenerationException if key is not set
    """
    if config.openai_api_key is None or config.openai_api_key == '':
        logger.error('OPENAI_API_KEY is not set. No response was generated.')
        raise ResponseGenerationException('OpenAI:n API-avain puuttuu ympäristömuuttujista')
    openai.api_key = config.openai_api_key


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


async def notify_message_author_has_no_permission_to_use_api(update: Update):
    await update.effective_message.reply_text('Komennon käyttö on rajattu pienelle testiryhmälle käyttäjiä')


def remove_openai_related_command_text_and_extra_info(text: str) -> str:
    text = remove_cost_so_far_notification_and_context_info(text)
    # Full path as it does not trigger circular dependency problems
    text = bobweb.bob.command_gpt.remove_gpt_command_related_text(text)
    text = bobweb.bob.command_image_generation.remove_all_dalle_and_dallemini_commands_related_text(text)
    return text


def remove_cost_so_far_notification_and_context_info(text: str) -> str:
    # Escape dollar signs and add decimal number matcher for each money amount
    decimal_number_pattern = r'\d*[,.]\d*'
    cost_so_far_pattern = OpenAiApiState.cost_so_far_template \
        .replace('$', r'\$') \
        .replace('{:f}', decimal_number_pattern)
    context_info_pattern = OpenAiApiState.gpt_context_message_count_template \
        .format(r'\d+', 'ä?')
    # Return with cost so far text removed and content stripped
    without_cost_text = re.sub(cost_so_far_pattern, '', text)
    without_context_info = re.sub(context_info_pattern, '', without_cost_text)
    return without_context_info.strip()


class OpenAiApiState:
    """ Class for OpenAiApi. Keeps track of cumulated costs since last restart """
    # Template for default addition to all OpenAi Api calls
    cost_so_far_template = 'Rahaa paloi: ${:f}, rahaa palanut rebootin jälkeen: ${:f}'

    # Template for ChatGpt message context size. As this is in Finnish, add single 'ä' to second
    # parameter if multiple messages, leave empty when single message
    gpt_context_message_count_template = 'Konteksti: {} viesti{}.'

    def __init__(self):
        self.__cost_so_far = 0

    def add_chat_gpt_cost_get_cost_str(self,
                                       model: GptModel,
                                       prompt_tokens: int,
                                       completion_tokens: int,
                                       context_msg_count: int):
        """
        Calculates cost of chatgpt call based on used model and its selected context token limit.
        Total cost depends on the context and response sizes.
        """
        context_cost = model.input_token_price * prompt_tokens / 1000
        response_cost = model.output_token_price * completion_tokens / 1000
        total_cost = context_cost + response_cost
        self.__cost_so_far += total_cost

        plural_ending = 'ä' if context_msg_count > 1 else ''
        context_info = self.gpt_context_message_count_template.format(context_msg_count, plural_ending)
        return context_info + " " + self.__get_formatted_cost_str(total_cost)

    def add_image_cost_get_cost_str(self, n: int, resolution: int):
        """ Dall-e image generation cost is number of generated images
            multiplied with single image price for used resolution """
        cost = n * image_generation_prices[resolution]
        self.__cost_so_far += cost
        return self.__get_formatted_cost_str(cost)

    def add_voice_transcription_cost_get_cost_str(self, duration_in_seconds: int):
        cost = duration_in_seconds / 60 * whisper_price_per_minute
        self.__cost_so_far += cost
        return self.__get_formatted_cost_str(cost)

    def get_cost_so_far(self):
        return self.__cost_so_far

    def reset_cost_so_far(self):
        self.__cost_so_far = 0

    def __get_formatted_cost_str(self, cost):
        return self.cost_so_far_template.format(cost, self.__cost_so_far)


"""
    Following tiktoken tokenizing and gpt context token calculation is for
    calculating size of request context before it is sent to OpenAi API. By
    default smallest available model is used for the requested version.
    Model is upgraded to one with larger model automatically, if users contexts
    token count exceeds default models limit.
"""
# Tiktoken: BPE tokeniser for use with OpenAi's models: https://github.com/openai/tiktoken
# cl100k_base works for both 'gpt-3.5-turbo' and 'gpt-4'
tiktoken_default_encoding_name = 'cl100k_base'


def token_count_from_message_list(messages: List[dict],
                                  model_for_tokenizing: GptModel) -> int:
    """
    Return the number of tokens used by a list of messages. NOTE! Supports only serialized message histories
    for the text models. Does not support counting token count for vision models.
    """
    try:
        encoding = tiktoken.encoding_for_model(model_for_tokenizing.name)
    except KeyError:
        print("Warning: model not found. Using cl100k_base encoding.")
        encoding = tiktoken.get_encoding(tiktoken_default_encoding_name)
    token_count = 3  # every reply is primed with <|start|>assistant<|message|>, so 3 is a constant token start count
    tokens_per_message = 3  # Each message in itself is 3 tokens plus token count of its content
    for message in messages:
        token_count += tokens_per_message + token_count_for_message(message, encoding)
    return token_count


def token_count_for_message(message: dict, encoding: Encoding) -> int:
    tokens_per_name = 1
    token_count = 0
    for key, value in message.items():
        token_count += len(encoding.encode(value))
        if key == "name":
            token_count += tokens_per_name
    return token_count


state = OpenAiApiState()

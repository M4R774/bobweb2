import logging
import re
from enum import Enum
from typing import List

from aiohttp import ClientResponse
from telegram import Update

import bobweb
from bobweb.bob import database, config
from bobweb.web.bobapp.models import TelegramUser

logger = logging.getLogger(__name__)

OPENAI_CHAT_COMPLETIONS_API_ENDPOINT = 'https://api.openai.com/v1/chat/completions'


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

    def __init__(self,
                 name,
                 major_version,
                 has_vision_capabilities,
                 token_limit,
                 message_serializer):
        self.name = name
        self.major_version = major_version
        self.has_vision_capabilities = has_vision_capabilities
        self.token_limit = token_limit
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
    name='gpt-3.5-turbo-0125',
    major_version=3,
    has_vision_capabilities=False,
    token_limit=16_385,
    message_serializer=msg_serializer_for_text_models
)

gpt_4o = GptModel(
    name='gpt-4o',
    major_version=4,
    has_vision_capabilities=True,
    token_limit=128_000,
    message_serializer=msg_serializer_for_vision_models
)

# All gpt models available for the bot to use. In priority from the lowest major version to the highest.
# Order inside major versions is by vision capability and then by token limit in ascending order.
ALL_GPT_MODELS = [gpt_3_16k, gpt_4o]


def determine_suitable_model_for_version_based_on_message_history(version: str,
                                                                  message_history: List[GptChatMessage]):
    """
    Determines used model based on the users requested gpt major version
    and the contents of the context message list.

    Tries to use requested major version. If context message list contains
    messages with images, then tries to find best suited model with vision
    capabilities.
    """
    match version:
        case '3' | '3.5':
            model = gpt_3_16k
        case _:
            model = gpt_4o

    for message in message_history:
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


safety_system_error_response_msg = ('OpenAi: Pyyntösi hylättiin turvajärjestelmämme seurauksena. Viestissäsi saattaa '
                                    'olla tekstiä, joka ei ole sallittu turvajärjestelmämme toimesta.')


async def handle_openai_response_not_ok(response: ClientResponse,
                                        general_error_response: str):
    """ Common error handler for all OpenAI API non 200 ok responses.
        API documentation: https://platform.openai.com/docs/guides/error-codes#api-errors """
    response_json = await response.json()
    error = response_json['error']
    error_code = error['code']
    message = error['message']

    # Default values if more exact reason cannot be extracted from response
    error_response_to_user = general_error_response
    log_message = f"OpenAI API request failed. [error_code]: {error_code} [message]:{message}"
    log_level = logging.ERROR

    # Expected error cases
    if response.status == 400 and error_code == 'content_policy_violation':
        error_response_to_user = safety_system_error_response_msg
        log_message = ("Generating dall-e image rejected due to content policy violation. "
                       f"[error_code]: {error_code} [message]:{message}")
        log_level = logging.INFO
    elif response.status == 401:
        error_response_to_user = 'Virhe autentikoitumisessa OpenAI:n järjestelmään.'
        log_message = f"OpenAI API authentication failed. [error_code]: {error_code} [message]:{message}"
        log_level = logging.ERROR
    elif response.status == 429 and ('quota' in error_code or 'quota' in message):
        error_response_to_user = 'Käytettävissä oleva kiintiö on käytetty.'
        log_message = f"OpenAI API quota limit reached. [error_code]: {error_code} [message]:{message}"
        log_level = logging.INFO
    elif response.status == 503 or (response.status == 429 and ('rate' in error_code or 'rate' in message)):
        error_response_to_user = ('OpenAi:n palvelu ei ole käytettävissä tai se on juuri nyt ruuhkautunut. '
                                  'Ole hyvä ja yritä hetken päästä uudelleen.')
        log_message = f"OpenAI API rate limit exceeded. [error_code]: {error_code} [message]:{message}"
        log_level = logging.INFO

    logger.log(level=log_level, msg=log_message)
    raise ResponseGenerationException(error_response_to_user)


def ensure_openai_api_key_set():
    """ Checks that openai api key is set. Raises ValueError if not set to environmental variable. """
    if config.openai_api_key is None or config.openai_api_key == '':
        logger.error('OPENAI_API_KEY is not set. No response was generated.')
        raise ResponseGenerationException('OpenAI API key is missing from environment variables')


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
    # Update 12/2024: Now bot no longer adds cost information to the replied message. However, as there are old
    # messages with cost information that the user might reply, this test is kept as it assures that the cost
    # information part is still removed as expected.
    cost_so_far_template = 'Rahaa paloi: ${:f}, rahaa palanut rebootin jälkeen: ${:f}'

    decimal_number_pattern = r'\d*[,.]\d*'
    cost_so_far_pattern = cost_so_far_template \
        .replace('$', r'\$') \
        .replace('{:f}', decimal_number_pattern)
    context_info_pattern = gpt_context_message_count_template \
        .format(r'\d+', 'ä?')
    # Return with cost so far text removed and content stripped
    without_cost_text = re.sub(cost_so_far_pattern, '', text)
    without_context_info = re.sub(context_info_pattern, '', without_cost_text)
    return without_context_info.strip()


# Template for ChatGpt message context size. As this is in Finnish, add single 'ä' to second
# parameter if multiple messages, leave empty when single message
gpt_context_message_count_template = 'Konteksti: {} viesti{}.'


def get_context_size_message(context_msg_count: int):
    plural_ending = 'ä' if context_msg_count > 1 else ''
    context_info = gpt_context_message_count_template.format(context_msg_count, plural_ending)
    return context_info

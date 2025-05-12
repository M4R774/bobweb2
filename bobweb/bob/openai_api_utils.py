import base64
import logging
import re
from typing import List, Callable

from aiohttp import ClientResponse
from telegram import Update

import bobweb
from bobweb.bob import database, config
from bobweb.bob.utils_common import ChatMessage
from bobweb.web.bobapp.models import TelegramUser

logger = logging.getLogger(__name__)

OPENAI_CHAT_COMPLETIONS_API_ENDPOINT = 'https://api.openai.com/v1/chat/completions'
CONTEXT_ROLE_SYSTEM = 'system'
CONTEXT_ROLE_USER = 'user'
CONTEXT_ROLE_ASSISTANT = 'assistant'

class GptModel:
    """
    Used GptModels. Value is a tuple of:
    (model, max_tokens, input price, output price)
    Model documentation: https://platform.openai.com/docs/models.
    Prices are per 1000 tokens. More info about pricing: https://openai.com/pricing.
    """

    def __init__(self,
                 name: str,
                 regex_matcher: str,
                 has_vision_capabilities: bool,
                 message_serializer: Callable[[ChatMessage], dict[str, str]],
                 context_role: str):
        self.name = name
        self.regex_matcher = regex_matcher
        self.has_vision_capabilities = has_vision_capabilities
        self.message_serializer = message_serializer
        self.context_role = context_role

    def serialize_message_history(self, messages: List[ChatMessage]) -> List[dict]:
        return [self.message_serializer(message) for message in messages]


def msg_serializer_for_text_models(message: ChatMessage) -> dict[str, str]:
    """ Creates message object for original GPT models without vision capabilities. """
    role = CONTEXT_ROLE_USER if message.origin.value == CONTEXT_ROLE_USER else CONTEXT_ROLE_ASSISTANT
    return {'role': role, 'content': message.text or ''}


def msg_serializer_for_vision_models(message: ChatMessage) -> dict[str, str]:
    """ Creates message object for GPT vision model. With vision model, content is a list of objects that can
        be either text messages or images"""
    content = []
    if message.text and message.text != '':
        content.append({'type': 'text', 'text': message.text})

    for image_url in message.images or []:
        if image_url and image_url != '':
            content.append({'type': 'image_url', 'image_url': {'url': image_url}})

    role = CONTEXT_ROLE_USER if message.origin.value == CONTEXT_ROLE_USER else CONTEXT_ROLE_ASSISTANT
    return {'role': role, 'content': content}


gpt_4o = GptModel(
    name='gpt-4o',
    regex_matcher='4|4o',
    has_vision_capabilities=True,
    message_serializer=msg_serializer_for_vision_models,
    context_role=CONTEXT_ROLE_SYSTEM
)

# o1 models and newer have different name for the system message
gpt_o1 = GptModel(
    name='o1-preview',
    regex_matcher='o1',
    has_vision_capabilities=False,
    message_serializer=msg_serializer_for_vision_models,
    context_role=CONTEXT_ROLE_USER
)

gpt_o1_mini = GptModel(
    name='o1-mini',
    regex_matcher='(o1)?-?mini',
    has_vision_capabilities=False,
    message_serializer=msg_serializer_for_vision_models,
    context_role=CONTEXT_ROLE_USER
)

# All gpt models available for the bot to use. In priority from the lowest major version to the highest.
# Order inside major versions is by vision capability and then by token limit in ascending order.
ALL_GPT_MODELS = [gpt_4o, gpt_o1_mini, gpt_o1]
ALL_GPT_MODELS_REGEX_MATCHER = f'({"|".join(model.regex_matcher for model in ALL_GPT_MODELS)})'
DEFAULT_MODEL = gpt_4o


def determine_suitable_model_for_version_based_on_message_history(version: str):
    """
    Determines used model based on the users requested gpt major version
    and the contents of the context message list.

    Tries to use requested major version. If context message list contains
    messages with images, then tries to find best suited model with vision
    capabilities.
    """
    if version is None or version == '':
        return DEFAULT_MODEL

    for gpt_model in ALL_GPT_MODELS:
        if re.fullmatch(gpt_model.regex_matcher, version.lower()):
            return gpt_model

    return DEFAULT_MODEL


# Custom Exception for errors caused by image generation
class ResponseGenerationException(Exception):
    def __init__(self, response_text):
        self.response_text = response_text  # Text that is sent back to chat


no_vision_capabilities = 'Pyydetty kielimalli ei tue kuvien käyttöä. Kokeile jotain seuraavaa mallia: '
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
    log_message = f'OpenAI API request failed. [error_code]: "{error_code}", [message]:"{message}"'
    log_level = logging.ERROR

    # Expected error cases
    if response.status == 400 and error_code in ['content_policy_violation', 'moderation_blocked']:
        error_response_to_user = safety_system_error_response_msg
        log_message = ("Generating AI image rejected due to content policy violation or moderation. "
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
    text = bobweb.bob.command_image_generation.remove_all_dalle_commands_related_text(text)
    return text


# Template for ChatGpt message context size. As this is in Finnish, add single 'ä' to second
# parameter if multiple messages, leave empty when single message
gpt_context_message_count_template = 'Konteksti: {} viesti{}.'


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

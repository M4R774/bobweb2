import logging
import re
from typing import List, Callable

from aiohttp import ClientResponse
from telegram import Update

import bot
from bot import database, config
from bot.utils_common import ChatMessage, ContentOrigin
from web.bobapp.models import TelegramUser
from bot.litellm_utils import ResponseGenerationException

logger = logging.getLogger(__name__)
OPENAI_CHAT_COMPLETIONS_API_ENDPOINT = 'https://api.openai.com/v1/chat/completions'

def msg_serializer_for_text_models(message: ChatMessage) -> dict[str, str]:
    """ Creates message object for original GPT models without vision capabilities. """
    return {'role': message.origin.value, 'content': message.text or ''}


def msg_serializer_for_vision_models(message: ChatMessage) -> dict[str, str]:
    """ Creates message object for GPT vision model. With vision model, content is a list of objects that can
        be either text messages or images"""
    content = []
    if message.text and message.text != '':
        content.append({'type': 'text', 'text': message.text})

    for image_url in message.images or []:
        if image_url and image_url != '':
            content.append({'type': 'image_url', 'image_url': {'url': image_url}})
    return {'role': message.origin.value, 'content': content}

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
    log_title = "OpenAI API request failed."
    log_level = logging.ERROR

    # Expected error cases
    if response.status == 400 and error_code in ['content_policy_violation', 'moderation_blocked']:
        error_response_to_user = safety_system_error_response_msg
        log_title = "Generating AI image rejected due to content policy violation or moderation."
        log_level = logging.INFO
    elif response.status == 401:
        error_response_to_user = 'Virhe autentikoitumisessa OpenAI:n järjestelmään.'
        log_title = "OpenAI API authentication failed."
        log_level = logging.ERROR
    elif response.status == 429 or error_code == "billing_hard_limit_reached" or error_code == "insufficient_quota":
        error_response_to_user = "Käytettävissä oleva kiintiö on käytetty."
        log_title = "OpenAI API quota limit reached."
        log_level = logging.INFO
    elif response.status == 503 or ('rate' in error_code or 'rate' in message):
        error_response_to_user = ('OpenAi:n palvelu ei ole käytettävissä tai se on juuri nyt ruuhkautunut. '
                                  'Ole hyvä ja yritä hetken päästä uudelleen.')
        log_title = "OpenAI API rate limit exceeded."
        log_level = logging.INFO

    log_message_with_details = (f'{log_title} [status]: {response.status}, [error_code]: "{error_code}", '
                                f'[message]: "{message}"')
    logger.log(level=log_level, msg=log_message_with_details)
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

    cc_holder_chat_ids = {chat.id for chat in cc_holder.chat_set.all()}
    author = database.get_telegram_user(user_id)
    author_chat_ids = {chat.id for chat in author.chat_set.all()}

    # Check if there is any overlap in cc_holder_chat_id_list and author_chat_id_list.
    # If so, return True, else return False
    return bool(cc_holder_chat_ids.intersection(author_chat_ids))


async def notify_message_author_has_no_permission_to_use_api(update: Update):
    await update.effective_message.reply_text('Komennon käyttö on rajattu pienelle testiryhmälle käyttäjiä')


def remove_openai_related_command_text_and_extra_info(text: str) -> str:
    text = remove_cost_so_far_notification_and_context_info(text)
    # Full path as it does not trigger circular dependency problems
    text = bot.commands.gpt.remove_gpt_command_related_text(text)
    text = bot.commands.image_generation.remove_all_dalle_commands_related_text(text)
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

import logging
import re
import string
from enum import Enum
from typing import List

import openai

from telegram import Update
from telegram.ext import CallbackContext
from telethon.tl.types import Message as TelethonMessage

from bobweb.bob import database, openai_api_utils, telethon_service
from bobweb.bob.command import ChatCommand, regex_simple_command_with_parameters, get_content_after_regex_match
from bobweb.bob.openai_api_utils import notify_message_author_has_no_permission_to_use_api, \
    ResponseGenerationException, OpenAiApiState, GptModel, find_gpt_model_name_by_version_number
from bobweb.bob.resources.bob_constants import PREFIXES_MATCHER
from bobweb.bob.utils_common import object_search, send_bot_is_typing_status_update
from bobweb.web.bobapp.models import Chat as ChatEntity

logger = logging.getLogger(__name__)

# Regexes for matching sub commands
system_prompt_pattern = regex_simple_command_with_parameters('system')
use_quick_system_pattern = rf'{PREFIXES_MATCHER}([123])'
use_quick_system_message_without_prompt_pattern = rf'(?i)^{use_quick_system_pattern}\s*$'
set_quick_system_pattern = rf'{PREFIXES_MATCHER}[123]\s*=\s*'


class ContextRole(Enum):
    SYSTEM = 'system'
    ASSISTANT = 'assistant'
    USER = 'user'
    FUNCTION = 'function'


class GptCommand(ChatCommand):
    invoke_on_edit = True
    invoke_on_reply = True

    def __init__(self):
        super().__init__(
            name='gpt',
            # 'gpt' with optional 3, 3.5 or 4 in the end
            regex=regex_simple_command_with_parameters(r'gpt(3)?(\.5)?4?'),
            help_text_short=('!gpt[3|4]', '[|1|2|3] [prompt] -> (gpt3.5|4) vastaus')
        )

    async def handle_update(self, update: Update, context: CallbackContext = None):
        """
        1. Check permission. If not, notify user
        2. Check has content after command. If not, notify user
        3. Check if message has any subcommand. If so, handle that
        4. Default: Handle as normal prompt
        """
        has_permission = openai_api_utils.user_has_permission_to_use_openai_api(update.effective_user.id)
        command_parameters = self.get_parameters(update.effective_message.text)
        if not has_permission:
            return await notify_message_author_has_no_permission_to_use_api(update)

        elif len(command_parameters) == 0:
            quick_system_prompts = database.get_quick_system_prompts(update.effective_message.chat_id)
            no_parameters_given_notification_msg = generate_no_parameters_given_notification_msg(quick_system_prompts)
            return await update.effective_chat.send_message(no_parameters_given_notification_msg)

        # if contains quick system message command without prompt
        elif re.search(use_quick_system_message_without_prompt_pattern, command_parameters) is not None:
            no_prompt_after_quick_system_message_selection = generate_no_parameters_given_notification_msg()
            return await update.effective_chat.send_message(no_prompt_after_quick_system_message_selection)

        # If contains update system prompt sub command
        elif re.search(system_prompt_pattern, command_parameters) is not None:
            await handle_system_prompt_sub_command(update, command_parameters)

        # If contains quick system set sub command
        elif re.search(set_quick_system_pattern, command_parameters) is not None:
            await handle_quick_system_set_sub_command(update, command_parameters)

        else:
            await gpt_command(update, context)

    def is_enabled_in(self, chat: ChatEntity):
        """ Is always enabled for chat. Users specific permission is specified when the update is handled """
        return True


async def gpt_command(update: Update, context: CallbackContext) -> None:
    """ Internal controller method of inputs and outputs for gpt-generation """
    started_reply_text = 'Vastauksen generointi aloitettu. Tämä vie 30-60 sekuntia.'
    started_reply = await update.effective_chat.send_message(started_reply_text)
    await send_bot_is_typing_status_update(update.effective_chat)

    try:
        reply = await generate_and_format_result_text(update)
    except ResponseGenerationException as e:  # If exception was raised, reply its response_text
        reply = e.response_text

    # All replies are as 'reply' to the prompt message to keep the message thread
    await update.effective_message.reply_text(reply, quote=True)

    # Delete notification message from the chat
    if context is not None:
        await context.bot.deleteMessage(chat_id=update.effective_message.chat_id,
                                        message_id=started_reply.message_id)


async def generate_and_format_result_text(update: Update) -> string:
    """ Determines system message, current message history and call api to generate response """
    system_message_obj: dict | None = determine_system_message(update)
    message_history: List[dict] = await form_message_history(update)
    context_msg_count = len(message_history)

    if system_message_obj is not None:
        message_history.insert(0, system_message_obj)

    openai_api_utils.ensure_openai_api_key_set()
    model: GptModel = determine_used_model_based_on_command_and_context(update.effective_message.text, message_history)

    response = openai.ChatCompletion.create(model=model.name, messages=message_history)
    content = response.choices[0].message.content

    cost_message = openai_api_utils.state.add_chat_gpt_cost_get_cost_str(
        model,
        response.usage.prompt_tokens,
        response.usage.completion_tokens,
        context_msg_count
    )
    response = f'{content}\n\n{cost_message}'
    return response


def determine_system_message(update: Update) -> dict | None:
    """ Returns either given quick system prompt or chats main system prompt """
    command_parameter = instance.get_parameters(update.effective_message.text)
    regex_match = re.match(rf'{PREFIXES_MATCHER}([123])', command_parameter)
    quick_system_parameter = regex_match[1] if regex_match is not None else None

    if quick_system_parameter is not None and quick_system_parameter != '':
        quick_system_prompts = database.get_quick_system_prompts(update.effective_chat.id)
        content = quick_system_prompts.get(quick_system_parameter, None)
    else:
        content = database.get_gpt_system_prompt(update.effective_chat.id)

    if content is None:
        return None
    return msg_obj(ContextRole.SYSTEM, content)


async def form_message_history(update: Update) -> List[dict]:
    """ Forms message history for reply chain. Latest message is last in the result list.
        This method uses both PTB (Telegram bot api) and Telethon (Telegram client api). """

    # First create object of current message
    cleaned_text = remove_gpt_command_related_text(update.effective_message.text)
    messages: list[dict] = [msg_obj(ContextRole.USER, cleaned_text)]

    # If current message is not a reply to any other, early return with it
    reply_to_msg = update.effective_message.reply_to_message
    if reply_to_msg is None:
        return messages

    # Now, current message is reply to another message that might be replied to another.
    # Iterate through the reply chain and find all messages in it
    next_id = reply_to_msg.message_id

    while next_id is not None:
        # Telethon api from here on. Find message with given id. If it was a reply to another message,
        # fetch that and repeat until no more messages are found in the reply thread
        current_message: TelethonMessage = await telethon_service.client.find_message(chat_id=update.effective_chat.id,
                                                                                      msg_id=next_id)
        sender = await telethon_service.client.find_user(current_message.from_id.user_id)

        # If author of message is bot, it's message is added with role assistant and
        # cost so far notification is removed from its messages
        if current_message.message is not None:
            if sender.bot:
                cleaned_message = remove_cost_so_far_notification_and_context_info(current_message.message)
                msg = msg_obj(ContextRole.ASSISTANT, cleaned_message)
            else:
                cleaned_message = remove_gpt_command_related_text(current_message.message)
                msg = msg_obj(ContextRole.USER, cleaned_message)

            # Now add the message to the list
            messages.append(msg)
            # Add next reply to reference if exists
            next_id = object_search(current_message, 'reply_to', 'reply_to_msg_id', default=None)

    messages.reverse()
    return messages


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


def remove_gpt_command_related_text(text: str) -> str:
    # remove gpt-command and possible quick system message sub-command
    pattern = rf'^({instance.regex})(\s*{PREFIXES_MATCHER}\S*)*\s*'
    result = re.sub(pattern, '', text)
    return result.strip()


def determine_used_model_based_on_command_and_context(message_text: str, message_history_list: List[dict]) -> GptModel:
    command_name_parameter = re.search(rf'(?i)^{PREFIXES_MATCHER}gpt(\d?\.?\d?)?', message_text)[1]
    return find_gpt_model_name_by_version_number(command_name_parameter, message_history_list)


def msg_obj(role: ContextRole, content: str) -> dict[str, str]:
    return {'role': role.value, 'content': content}


async def handle_quick_system_set_sub_command(update: Update, command_parameter):
    sub_command = command_parameter[1]
    sub_command_parameter = get_content_after_regex_match(command_parameter, set_quick_system_pattern)

    quick_system_prompts = database.get_quick_system_prompts(update.effective_message.chat_id)
    current_prompt = quick_system_prompts.get(sub_command, None)

    # If actual prompt after quick system set option is empty
    if sub_command_parameter.strip() == '':
        empty_message_last_part = f" tyhjä. Voit asettaa pikaohjausviestin sisällön komennolla '/gpt {sub_command} = (uusi viesti)'."
        current_message_msg = empty_message_last_part if current_prompt is None else f':\n\n{current_prompt}'
        await update.effective_message.reply_text(
            f"Nykyinen pikaohjausviesti {sub_command} on nyt{current_message_msg}")
    else:
        database.set_quick_system_prompt(update.effective_chat.id, sub_command, sub_command_parameter)
        await update.effective_message.reply_text(f"Uusi pikaohjausviesti {sub_command} asetettu.")


def generate_no_parameters_given_notification_msg(quick_system_prompts: dict = None):
    if quick_system_prompts:
        quick_system_prompts_str = ''.join([f'\n{key}: {value}' for key, value in quick_system_prompts.items()])
    else:
        quick_system_prompts_str = ''
    no_parameters_given_notification_msg = \
        f'Anna jokin syöte komennon jälkeen. [.!/]gpt (syöte). Voit valita jonkin kolmesta valmiista ' \
        f'ohjeistusviestistä laittamalla numeron 1-3 ennen syötettä. {quick_system_prompts_str}'
    return no_parameters_given_notification_msg


async def handle_system_prompt_sub_command(update: Update, command_parameter):
    sub_command_parameter = get_content_after_regex_match(command_parameter, system_prompt_pattern)
    # If sub command parameter is empty, print current system prompt. Otherwise, update system prompt for chat
    if sub_command_parameter is None or sub_command_parameter.strip() == '':
        current_prompt = database.get_gpt_system_prompt(update.effective_chat.id)
        empty_message_last_part = " tyhjä. Voit asettaa system-viestin sisällön komennolla '/gpt /system {uusi viesti}'."
        current_message_msg = empty_message_last_part if current_prompt is None else f':\n\n{current_prompt}'
        await update.effective_message.reply_text(f"Nykyinen system-viesti on nyt{current_message_msg}")
    else:
        database.set_gpt_system_prompt(update.effective_chat.id, sub_command_parameter)
        await update.effective_message.reply_text("System-viesti asetettu annetuksi.", quote=True)


# Single instance of these classes
instance = GptCommand()

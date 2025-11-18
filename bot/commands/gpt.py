import logging
import re
import string
from typing import List, Optional

import django
from telegram import Update, LinkPreviewOptions
from telegram.constants import ParseMode
from telegram.ext import CallbackContext

from bot import database, openai_api_utils, telethon_service, google_genai_api_utils
from bot.commands.base_command import BaseCommand, regex_simple_command_with_parameters, get_content_after_regex_match
from bot.openai_api_utils import notify_message_author_has_no_permission_to_use_api, \
    ALL_GPT_MODELS_REGEX_MATCHER, \
    msg_serializer_for_vision_models, ContentOrigin
from bot.litellm_utils import acompletion, ResponseGenerationException
from bot.resources.bob_constants import PREFIXES_MATCHER
from bot.telethon_service import ChatMessage
from bot.utils_common import object_search, send_bot_is_typing_status_update, reply_long_text_with_markdown
from web.bobapp.models import Chat as ChatEntity

SYSTEM_MESSAGE_SET = "System-viesti asetettu annetuksi."

CURRENT_MODEL = "gemini/gemini-3-pro-preview"

logger = logging.getLogger(__name__)


class GptCommand(BaseCommand):
    invoke_on_edit = True
    invoke_on_reply = True

    def __init__(self):
        super().__init__(
            name='gpt',
            # 'gpt' with optional 4, 4o, o1 or o1-mini in the end
            regex=regex_simple_command_with_parameters(rf'gpt{ALL_GPT_MODELS_REGEX_MATCHER}?'),
            help_text_short=('!gpt[model] {prompt}', 'vastaus')
        )

    async def handle_update(self, update: Update, context: CallbackContext = None):
        """
        1. Check permission. If not, notify user
        2. Check that has content after command or is reply to another message. If not, notify user
        3. Check if message has any subcommand. If so, handle that
        4. Default: Handle as normal prompt
        """
        has_permission = openai_api_utils.user_has_permission_to_use_openai_api(update.effective_user.id)
        command_parameters = self.get_parameters(update.effective_message.text)

        has_content_after_command = len(command_parameters) > 0
        is_reply_to_message = update.effective_message.reply_to_message is not None
        has_image_media = update.effective_message.photo is not None and len(update.effective_message.photo) > 0

        if not has_permission:
            return await notify_message_author_has_no_permission_to_use_api(update)

        contains_help_sub_command = re.search(help_sub_command_pattern, command_parameters) is not None
        # If command has no parameters and is not reply to another message -> give info message.
        # If is reply to another message or if contains any image media, process normally
        command_has_no_context = not has_content_after_command and not is_reply_to_message and not has_image_media
        # if contains quick system message command without prompt
        quick_system_prompt_no_context = (re.search(use_quick_system_message_without_prompt_pattern, command_parameters)
                                          is not None)
        if contains_help_sub_command or command_has_no_context or quick_system_prompt_no_context:
            help_message = generate_help_message(update.effective_chat.id)
            link_preview_options = LinkPreviewOptions(is_disabled=True)
            return await update.effective_chat.send_message(
                help_message, link_preview_options=link_preview_options, parse_mode=ParseMode.HTML)

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


def generate_help_message(chat_id: int) -> str:
    system_prompt = database.get_gpt_system_prompt(chat_id)
    if system_prompt is not None:
        context = {'current_system_prompt': django.utils.html.escape(system_prompt)}
        current_system_prompt_part = system_prompt_template.safe_substitute(context)
    else:
        current_system_prompt_part = no_system_prompt_paragraph

    quick_system_prompts = database.get_quick_system_prompts(chat_id)
    if quick_system_prompts:
        quick_system_list_items = [create_quick_system_prompt_item_text(item) for item in quick_system_prompts.items()]
        quick_system_prompts_str = ''.join(quick_system_list_items)
        context = {'quick_system_prompts': quick_system_prompts_str}
        current_system_prompt_part = quick_system_prompts_template.safe_substitute(context)
    else:
        quick_system_prompts_str = no_quick_system_prompts_paragraph

    template_variables = {
        'default_model_name': CURRENT_MODEL,
        'current_system_prompt_paragraph': current_system_prompt_part,
        'quick_system_prompts': quick_system_prompts_str
    }
    return help_message_template.safe_substitute(template_variables)


def create_quick_system_prompt_item_text(item) -> str:
    key, value = item
    return f'- {key}: "<i>{django.utils.html.escape(value)}</i>"\n'


async def gpt_command(update: Update, context: CallbackContext) -> None:
    """ Internal controller method of inputs and outputs for gpt-generation """
    started_reply_text = 'Vastauksen generointi aloitettu. Tämä vie 10-30 sekuntia.'
    started_reply = await update.effective_chat.send_message(started_reply_text)

    use_quote = True
    try:
        reply = await generate_and_format_result_text(update)
    except ResponseGenerationException as e:  # If exception was raised, reply its response_text
        use_quote = False
        reply = e.response_text

    # All replies are as 'reply' to the prompt message to keep the message thread.
    # Use wrapped reply method that sends text in multiple messages if it is too long.
    await reply_long_text_with_markdown(update, reply, do_quote=use_quote)

    # Delete notification message from the chat
    await update.effective_chat.delete_message(started_reply.message_id)


async def generate_and_format_result_text(update: Update) -> string:
    """ Determines system message, current message history and call api to generate response """
    google_genai_api_utils.ensure_gemini_api_key_set()

    message_history: List[ChatMessage] = await telethon_service.form_message_history(update)

    system_message_obj: ChatMessage = determine_system_message(update, context_role=ContentOrigin.SYSTEM)
    if system_message_obj is not None:
        message_history.insert(0, system_message_obj)

    messages: List[dict] = [msg_serializer_for_vision_models(message) for message in message_history]

    await send_bot_is_typing_status_update(update.effective_chat)

    response = await acompletion(
            model=CURRENT_MODEL,
            messages=messages
    )

    return object_search(response, 'choices', 0, 'message', 'content')


def remove_gpt_command_related_text(text: str) -> str:
    # remove gpt-command and any sub commands
    pattern = extract_model_name_pattern + '?[123]?'
    return re.sub(pattern, '', text).strip()


def determine_system_message(update: Update, context_role: ContentOrigin) -> Optional[ChatMessage]:
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
    return ChatMessage(context_role, content)


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
        await update.effective_message.reply_text(SYSTEM_MESSAGE_SET, do_quote=True)


# Regexes for matching sub commands
help_sub_command_pattern = rf'{PREFIXES_MATCHER}?help\s*$'
extract_model_name_pattern = rf'(?i)^{PREFIXES_MATCHER}gpt\s?{PREFIXES_MATCHER}?{ALL_GPT_MODELS_REGEX_MATCHER}'
system_prompt_pattern = regex_simple_command_with_parameters('system', command_prefix_is_optional=True)
use_quick_system_pattern = rf'{PREFIXES_MATCHER}?([123])'
use_quick_system_message_without_prompt_pattern = rf'(?i)^{use_quick_system_pattern}\s*$'
set_quick_system_pattern = rf'{PREFIXES_MATCHER}?[123]\s*=\s*'

system_prompt_template: string.Template = string.Template(
    '<b>Tämän chatin järjestelmäviesti on:</b>\n'
    '"""\n'
    '<i>${current_system_prompt}</i>\n'
    '"""')
quick_system_prompts_template: string.Template = string.Template(
    '<b>Tämän chatin pikajärjestelmäviestit ovat:</b>\n'
    '"""\n'
    '${quick_system_prompts}'
    '"""')
no_system_prompt_paragraph = '<b>Järjestelmäviestiä ei ole vielä asetettu tähän chattiin.</b>\n'
no_quick_system_prompts_paragraph = '<b>Pikajärjestelmäviestejä ei ole vielä asetettu tähän chattiin.</b>\n'

help_message_template_string_content = \
    ('<code>/gpt</code> komennolla voi käyttää ulkomaisia kielimalleja. Perusmuotoisena komento annetaan '
     'muodossa <code>/gpt {syöte}</code>. Kielimallille lähetetään komennon sisältävä viesti mahdollisen kuvamedian '
     'kera sekä kaikki samassa vastausketjussa (reply) olevat viestit niiden sisältämän tekstin ja kuvien osalta. '
     'Oletuksena kielimallina käytetään <b>${default_model_name}</b>:ta.\n'
     '\n'
     '<b>Kielimallille annettu pysyvä ohje (järjestelmäviesti):</b>\n'
     '<blockquote expandable>'
     'Jokaisen komennon yhteydessä kielimallille lähetetään järjestelmäviesti joka on sille ohjeistus kuinka käsitellä '
     'viestiketjussa olevia viestejä. Järjestelmäviesti tallennetaan chat-kohtaisesti ja sitä voi muuttaa komennolla '
     '\'/gpt /system {uusi järjestelmäviesti}\'.\n'
     '\n'
     '${current_system_prompt_paragraph}'
     '</blockquote>\n'
     '\n'
     '<b>Kielimallille annettu pysyvä ohje (järjestelmäsyöte):</b>\n'
     '<blockquote expandable>'
     'Oletusarvoisen järjestelmäsyötteen sijaan voit valita jonkin muista ennalta tallennetuista '
     'pikajärjestelmäviesteistä. Järjestelmäviestin voit valita lisäämällä komennon perään sen numeron. Viestejä voi '
     'tallentaa chat kohtaisiin muistipaikkoihin 1, 2 ja 3.\n'
     '\n'
     '<i>Pikajärjestelmäviestin käyttäminen:</i>\n'
     '- `/gpt /1 {syöte}`\n'
     '- `/gpt .2 {syöte}`\n'
     '- `/gpt !3 {syöte}`\n'
     '\n'
     '<i>Pikajärjestelmäviestin asettaminen:</i>\n'
     '- `/gpt /{numero} = {uusi pikajärjestelmäviesti}\n'
     '\n'
     '${quick_system_prompts}'
     '</blockquote>')
help_message_template: string.Template = string.Template(help_message_template_string_content)

# Single instance of these classes
instance = GptCommand()

import logging
import re
import string
import os

import openai

from telegram import Update
from telegram.ext import CallbackContext

from bobweb.bob import database
from bobweb.bob.command import ChatCommand, regex_simple_command_with_parameters, regex_simple_command, \
    get_content_after_regex_match
from bobweb.web.bobapp.models import Chat, TelegramUser

logger = logging.getLogger(__name__)

# Regexes for matching sub commands
system_prompt_sub_command_regex = regex_simple_command_with_parameters('system')
reset_chat_context_sub_command_regex = regex_simple_command('reset')


class GptCommand(ChatCommand):
    # Static context attributes
    run_async = True  # Should be asynchronous

    def __init__(self):
        super().__init__(
            name='gpt',
            regex=regex_simple_command_with_parameters('gpt'),
            help_text_short=('!gpt', '[prompt] -> vastaus')
        )
        # How many messages Bot remembers
        self.conversation_context_length = 20

        # Dict - Key: chatId, value: Conversation list
        self.conversation_context = {}
        self.costs_so_far = 0

    def handle_update(self, update: Update, context: CallbackContext = None):
        """
        1. Check permission. If not, notify user
        2. Check has content after command. If not, notify user
        3. Check if message has any subcommand. If so, handle that
        4. Default: Handle as normal prompt
        """
        has_permission = does_user_have_permission_to_use_command(update)
        command_parameter = self.get_parameters(update.effective_message.text)
        if not has_permission:
            return update.effective_message.reply_text('Komennon käyttö on rajattu pienelle testiryhmälle käyttäjiä')

        elif len(command_parameter) == 0:
            return update.effective_chat.send_message(no_parameters_given_notification_msg)

        # If contains update system prompt sub command
        elif re.search(system_prompt_sub_command_regex, command_parameter) is not None:
            handle_system_prompt_sub_command(update, command_parameter)

        # If contains reset chat conversation context sub command
        elif re.search(reset_chat_context_sub_command_regex, command_parameter) is not None:
            self.reset_chat_conversation_context(update)

        else:
            self.gpt_command(update, command_parameter, context)

    def is_enabled_in(self, chat: Chat):
        """ Is always enabled for chat. Users specific permission is specified when the update is handled """
        return True

    def gpt_command(self, update: Update, new_prompt: str, context: CallbackContext = None) -> None:
        started_reply_text = 'Vastauksen generointi aloitettu. Tämä vie 30-60 sekuntia.'
        started_reply = update.effective_chat.send_message(started_reply_text)
        self.add_context(update.effective_chat.id, "user", new_prompt)
        self.handle_response_generation_and_reply(update)

        # Delete notification message from the chat
        if context is not None:
            context.bot.deleteMessage(chat_id=update.effective_message.chat_id,
                                      message_id=started_reply.message_id)

    def reset_chat_conversation_context(self, update):
        self.conversation_context[update.effective_chat.id] = []
        update.effective_chat.send_message('Gpt viestihistoria tyhjennetty')

    def add_context(self, chat_id: int, role: str, content: str):
        if self.conversation_context.get(chat_id) is None:
            self.conversation_context[chat_id] = []

        self.conversation_context.get(chat_id).append({'role': role, 'content': content})
        if len(self.conversation_context.get(chat_id)) > self.conversation_context_length:
            self.conversation_context.get(chat_id).pop(0)

    def handle_response_generation_and_reply(self, update: Update) -> None:
        try:
            text_compilation = self.generate_and_format_result_text(update.effective_chat.id)
            update.effective_message.reply_text(text_compilation)
        except ResponseGenerationException as e:  # If exception was raised, reply its response_text
            update.effective_message.reply_text(e.response_text, quote=True)

    def generate_and_format_result_text(self, chat_id: int) -> string:
        if os.getenv('OPENAI_API_KEY') is None or os.getenv("OPENAI_API_KEY") == "":
            logger.error('OPENAI_API_KEY is not set.')
            return "OPENAI_API_KEY ei ole asetettuna ympäristömuuttujiin."
        openai.api_key = os.getenv('OPENAI_API_KEY')
        completion = openai.ChatCompletion.create(
            model='gpt-3.5-turbo',
            messages=self.build_message(chat_id)
        )
        content = completion.choices[0].message.content
        self.add_context(chat_id, "assistant", content)

        cost = completion.usage.total_tokens * 0.002 / 1000
        self.costs_so_far += cost
        cost_message = 'Rahaa paloi: ${:f}, rahaa palanut rebootin jälkeen: ${:f}'.format(cost, self.costs_so_far)
        response = '{}\n\n{}'.format(content, cost_message)
        return response

    def build_message(self, chat_id: int):
        system_prompt = database.get_gpt_system_prompt(chat_id)
        return [{'role': 'system', 'content': system_prompt}] + self.conversation_context.get(chat_id)


no_parameters_given_notification_msg = "Anna jokin syöte komennon jälkeen. '[.!/]gpt {syöte}'. Voit asettaa ChatGpt:n" \
                                       "System-viestin komennolla '[.!/]gpt [.!/]system {uusi system viesti}'. " \
                                       "System-viesti on kaikissa muissa viesteissä mukana menevä metatieto botille " \
                                       "jolla voi esimerkiksi ohjeistaa halutun tyylin vastata viesteihin."


def handle_system_prompt_sub_command(update: Update, command_parameter):
    sub_command_parameter = get_content_after_regex_match(command_parameter, system_prompt_sub_command_regex)
    # If sub command parameter is empty, print current system prompt. Otherwise, update system prompt for chat
    if sub_command_parameter.strip() == '':
        current_prompt = database.get_gpt_system_prompt(update.effective_chat.id)
        empty_message_last_part = " tyhjä. Voit asettaa system-viestin sisällön komennolla '/gpt /system {uusi viesti}'."
        current_message_msg = empty_message_last_part if current_prompt is None else f':\n\n{current_prompt}'
        update.effective_message.reply_text(f"Nykyinen system-viesti on nyt{current_message_msg}")
    else:
        database.set_gpt_system_prompt(update.effective_chat.id, sub_command_parameter)
        chat_system_prompt = database.get_gpt_system_prompt(update.effective_chat.id)
        update.effective_message.reply_text("Uusi system-viesti on nyt:\n\n" + chat_system_prompt)


def does_user_have_permission_to_use_command(update: Update) -> bool:
    """ Message author has permission to use command if message author is
        credit card holder or message author and credit card holder have a common chat"""
    cc_holder: TelegramUser = database.get_credit_card_holder()
    if cc_holder is None:
        return False

    cc_holder_chat_ids = set(chat.id for chat in cc_holder.chat_set.all())
    author = database.get_telegram_user(update.effective_user.id)
    author_chat_ids = set(chat.id for chat in author.chat_set.all())

    # Check if there is any overlap in cc_holder_chat_id_list and author_chat_id_list.
    # If so, return True, else return False
    return bool(cc_holder_chat_ids.intersection(author_chat_ids))


# Custom Exception for errors caused by response generation
class ResponseGenerationException(Exception):
    def __init__(self, response_text):
        self.response_text = response_text  # Text that is sent back to chat


# Single instance of this class
instance = GptCommand()

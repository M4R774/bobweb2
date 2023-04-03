import logging
import string
import os

import openai

from telegram import Update
from telegram.ext import CallbackContext

from bobweb.bob import database
from bobweb.bob.command import ChatCommand, regex_simple_command_with_parameters
from bobweb.web.bobapp.models import Chat, TelegramUser

logger = logging.getLogger(__name__)


class GptCommand(ChatCommand):
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
        has_permission = does_user_have_permission_to_use_command(update)
        if not has_permission:
            update.effective_message.reply_text('Komennon käyttö on rajattu pienelle testiryhmälle käyttäjiä')
            return
        if update.effective_user.id == database.get_credit_card_holder().id and \
                update.effective_message.text.startswith(".gpt .system"):
            database.set_gpt_system_prompt(update.effective_message.text[13:])
            update.effective_message.reply_text("Uusi system-viesti on nyt:\n\n" + database.get_gpt_system_prompt())
        else:
            self.gpt_command(update, context)

    def is_enabled_in(self, chat: Chat):
        """ Is always enabled for chat. Users specific permission is specified when the update is handled """
        return True

    def gpt_command(self, update: Update, context: CallbackContext = None) -> None:
        new_prompt = self.get_parameters(update.effective_message.text)

        if not new_prompt:
            update.effective_message.reply_text("Anna jokin syöte komennon jälkeen. '[.!/]gpt [syöte]'", quote=False)
            return
        started_reply_text = 'Vastauksen generointi aloitettu. Tämä vie 30-60 sekuntia.'
        started_reply = update.effective_message.reply_text(started_reply_text, quote=False)
        self.add_context(update.effective_chat.id, "user", new_prompt)
        self.handle_response_generation_and_reply(update)

        # Delete notification message from the chat
        if context is not None:
            context.bot.deleteMessage(chat_id=update.effective_message.chat_id,
                                      message_id=started_reply.message_id)

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
        return [{'role': 'system', 'content': database.get_gpt_system_prompt()}] + self.conversation_context.get(chat_id)


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

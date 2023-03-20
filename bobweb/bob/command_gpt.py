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
    conversation_context_length = 20  # How many messages Bot remembers
    conversation_context = []
    costs_so_far = 0

    def __init__(self):
        super().__init__(
            name='gpt',
            regex=regex_simple_command_with_parameters('gpt'),
            help_text_short=('!gpt', '[prompt] -> vastaus')
        )

    def add_context(self, update: Update, context: CallbackContext = None):
        if len(self.conversation_context) < self.conversation_context_length:
            self.conversation_context.append(update)
        else:
            self.conversation_context.pop(0)
            self.conversation_context.append(update)

    def handle_update(self, update: Update, context: CallbackContext = None):
        if update.effective_user.id == database.get_credit_card_holder().id and \
                update.effective_message.text.startswith(".gpt .system"):
            database.set_gpt_system_prompt(update.effective_message.text[13:])
            update.effective_message.reply_text("Uusi system-viesti on nyt:\n\n" + database.get_gpt_system_prompt())
        else:
            self.gpt_command(update, context)

    def is_enabled_in(self, chat: Chat):
        credit_card_holder: TelegramUser = database.get_credit_card_holder()
        if credit_card_holder is not None:
            if chat.id == credit_card_holder.id:
                return True

            chat_members = database.get_chat_members_for_chat(chat.id)
            for chat_member in chat_members:
                if credit_card_holder.id == chat_member.id:
                    return True
        return False

    def gpt_command(self, update: Update, context: CallbackContext = None) -> None:
        prompt = self.build_prompt_from_context()

        if not prompt:
            update.effective_message.reply_text("Anna jokin syöte komennon jälkeen. '[.!/]gpt [syöte]'", quote=False)
        else:
            started_notification = update.effective_message.reply_text('Vastauksen generointi aloitettu.'
                                                                       ' Tämä vie 30-60 sekuntia.', quote=False)

            self.handle_response_generation_and_reply(update, prompt)

            # Delete notification message from the chat
            if context is not None:
                context.bot.deleteMessage(chat_id=update.effective_message.chat_id,
                                          message_id=started_notification.message_id)

    def build_prompt_from_context(self):
        prompt = "Last " + str(self.conversation_context_length) + " messages from the chat: '"
        for update in self.conversation_context:
            if update.effective_message.text is not None:
                prompt += str(database.get_telegram_user(update.effective_user.id)) + ": " \
                          + update.effective_message.text + "\n\n"
        prompt += "'. The last message starting with .gpt is addressed directly to you. "
        return prompt

    def generate_and_format_result_text(self, prompt: string) -> string:
        if os.getenv('OPENAI_API_KEY') is None:
            logger.error('OPENAI_API_KEY is not set.')
            return "OPENAI_API_KEY ei ole asetettuna ympäristömuuttujiin."
        openai.api_key = os.getenv('OPENAI_API_KEY')
        completion = openai.ChatCompletion.create(
            model='gpt-3.5-turbo',
            messages=[
                    {'role': 'system', 'content': database.get_gpt_system_prompt()},
                    {'role': 'user', 'content': prompt}
                ]
        )
        content = completion.choices[0].message.content

        cost = completion.usage.total_tokens * 0.002 / 1000
        self.costs_so_far += cost
        cost_message = 'Rahaa paloi: ${:f}, rahaa palanut rebootin jälkeen: ${:f}'.format(cost, self.costs_so_far)
        response = '{}\n\n{}'.format(content, cost_message)
        return response

    def handle_response_generation_and_reply(self, update: Update, prompt: string) -> None:
        try:
            text_compilation = self.generate_and_format_result_text(prompt)
            update.effective_message.reply_text(text_compilation)

        except ResponseGenerationException as e:  # If exception was raised, reply its response_text
            update.effective_message.reply_text(e.response_text, quote=True)


# Custom Exception for errors caused by response generation
class ResponseGenerationException(Exception):
    def __init__(self, response_text):
        self.response_text = response_text  # Text that is sent back to chat

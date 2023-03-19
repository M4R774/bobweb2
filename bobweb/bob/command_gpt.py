import logging
import string
import os

import openai

from telegram import Update
from telegram.ext import CallbackContext

from bobweb.bob.command import ChatCommand, regex_simple_command_with_parameters

logger = logging.getLogger(__name__)


class GptCommand(ChatCommand):
    run_async = True  # Should be asynchronous

    def __init__(self):
        super().__init__(
            name='gpt',
            regex=regex_simple_command_with_parameters('gpt'),
            help_text_short=('!gpt', '[prompt] -> vastaus')
        )

    def handle_update(self, update: Update, context: CallbackContext = None):
        self.gpt_command(update, context)

    def is_enabled_in(self, chat):
        return chat.leet_enabled

    def gpt_command(self, update: Update, context: CallbackContext = None) -> None:
        prompt = self.get_parameters(update.effective_message.text)

        if not prompt:
            update.effective_message.reply_text("Anna jokin syöte komennon jälkeen. '[.!/]gpt [syöte]'", quote=False)
        else:
            started_notification = update.effective_message.reply_text('Vastauksen generointi aloitettu. Tämä vie 30-60 sekuntia.', quote=False)
            handle_response_generation_and_reply(update, prompt)

            # Delete notification message from the chat
            if context is not None:
                context.bot.deleteMessage(chat_id=update.effective_message.chat_id, message_id=started_notification.message_id)


def handle_response_generation_and_reply(update: Update, prompt: string) -> None:
    try:
        text_compilation = generate_and_format_result_text(prompt)
        update.effective_message.reply_text(text_compilation)

    except ResponseGenerationException as e:  # If exception was raised, reply its response_text
        update.effective_message.reply_text(e.response_text, quote=True)


def generate_and_format_result_text(prompt: string) -> string:
    if os.getenv('OPENAI_API_KEY') is None:
        logger.error('OPENAI_API_KEY is not set.')
        raise EnvironmentError
    openai.api_key = os.getenv('OPENAI_API_KEY')
    completion = openai.ChatCompletion.create(
        model='gpt-3.5-turbo',
        messages=[
                {'role': 'system', 'content': 'You are a helpful assistant.'},
                {'role': 'user', 'content': prompt}
            ]
    )
    content = completion.choices[0].message.content
    cost = 'Cost of this query was: ${:f}'.format(completion.usage.total_tokens * 0.002 / 1000)
    response = '{}\n\n{}'.format(content, cost)
    return response


# Custom Exception for errors caused by response generation
class ResponseGenerationException(Exception):
    def __init__(self, response_text):
        self.response_text = response_text  # Text that is sent back to chat

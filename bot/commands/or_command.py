import string

from telegram import Update
from telegram.ext import CallbackContext

from bot.commands.base_command import BaseCommand
from bot.resources.bob_constants import PREFIXES_MATCHER
import random
import re


class OrCommand(BaseCommand):
    def __init__(self):
        super().__init__(
            name='vai',
            regex=rf'\s{PREFIXES_MATCHER}vai\s',  # any text and whitespace before and after the command
            help_text_short=('.. !vai ..', 'Arpoo toisen')
        )

    async def handle_update(self, update: Update, context: CallbackContext = None):
        options = self.get_parameters(update.effective_message.text)
        if len(options) > 1:
            reply = random.choice(options)  # NOSONAR
            reply = reply.rstrip("?")
            if reply and reply is not None:
                await update.effective_message.reply_text(reply)

    def is_enabled_in(self, chat):
        return chat.or_enabled

    def get_parameters(self, text: string) -> list[string]:
        return [i.strip() for i in re.split(self.regex, text)]


from telegram import Update
from telegram.ext import CallbackContext

from command import ChatCommand
from resources.bob_constants import PREFIXES_MATCHER
import random
import re


class OrCommand(ChatCommand):
    def __init__(self):
        super().__init__(
            name='vai',
            regex=r'.*\s' + PREFIXES_MATCHER + 'vai\s.*',  # any text and whitespace before and after the command
            help_text_short=('.. !vai ..', 'Arpoo toisen')
        )

    def handle_update(self, update: Update, context: CallbackContext = None):
        or_command(update)

    def is_enabled_in(self, chat):
        return chat.or_enabled


def or_command(update):
    options = re.split(r'\s.vai\s', update.message.text)
    options = [i.strip() for i in options]
    reply = random.choice(options)
    reply = reply.rstrip("?")
    if reply and reply is not None:
        update.message.reply_text(reply)

from abstract_command import AbstractCommand
from bob_constants import PREFIXES_MATCHER
import random
import re


class OrCommand(AbstractCommand):
    def __init__(self):
        super().__init__(
            'vai',
            r'.*\s' + PREFIXES_MATCHER + 'vai\s.*',  # any text and whitespace before and after the command
            ('.. !vai ..', 'Arpoo jomman kumman')
        )

    def handle_update(self, update):
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

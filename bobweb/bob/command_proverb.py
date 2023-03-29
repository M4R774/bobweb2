from telegram import Update
from telegram.ext import CallbackContext

from bobweb.bob.command import ChatCommand, regex_simple_command


class ProverbCommand(ChatCommand):
    def __init__(self):
        super().__init__(
            name='viisaus',
            regex=regex_simple_command('viisaus'),
            help_text_short=('!viisaus', 'Sananlaskuja yms.')
        )

    def handle_update(self, update: Update, context: CallbackContext = None):
        reply_text = "TODO"
        update.effective_message.reply_text(reply_text)

    def is_enabled_in(self, chat):
        return True


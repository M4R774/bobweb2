import string

from telegram import Update
from telegram.ext import CallbackContext

from command import ChatCommand
from resources.bob_constants import PREFIXES_MATCHER
import database


# Manages detecting a daily question and commands for it
class KysymysCommand(ChatCommand):
    def __init__(self):
        super().__init__(
            name='päivänkysymys',
            regex=r'(?i)#päivänkysymys',
            help_text_short=('#päivänkysymys', '[on|off]')
        )

    def handle_update(self, update: Update, context: CallbackContext = None):
        self.handle_update_with_kysymys(update)

    def is_enabled_in(self, chat):
        return True  # This command is always enabled. Chat.broadcast_enabled toggles broadcasts in the chat

    def handle_update_with_kysymys(self, update):
        update.message.reply_text('kysymys', quote=False)

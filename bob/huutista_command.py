from telegram import Update
from telegram.ext import CallbackContext

from chat_command import ChatCommand

class HuutistaCommand(ChatCommand):
    def __init__(self):
        super().__init__(
            name='huutista',
            regex=r'(?i)huutista',  # (?i) => case insensitive
            help_text_short=('huutista', '😂')
        )

    def handle_update(self, update: Update, context: CallbackContext = None):
        update.message.reply_text('...joka tuutista! 😂')

    def is_enabled_in(self, chat):
        return chat.huutista_enabled

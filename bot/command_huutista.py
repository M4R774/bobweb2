from telegram import Update
from telegram.ext import CallbackContext

from bot.command import ChatCommand

class HuutistaCommand(ChatCommand):
    def __init__(self):
        super().__init__(
            name='huutista',
            regex=r'(?i)^huutista$',  # Note! No command prefix, (?i) => case insensitive, $ => end of string
            help_text_short=('huutista', '😂')
        )

    async def handle_update(self, update: Update, context: CallbackContext = None):
        await update.effective_message.reply_text('...joka tuutista! 😂', do_quote=False)

    def is_enabled_in(self, chat):
        return chat.huutista_enabled

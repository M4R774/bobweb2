from telegram.ext import CallbackContext

from bot.command import ChatCommand, regex_simple_command
from bot.resources.bob_constants import fitz
from telegram import Update
import datetime


class AikaCommand(ChatCommand):
    def __init__(self):
        super().__init__(
            name='aika',
            regex=regex_simple_command('aika'),
            help_text_short=('!aika', 'Kertoo ajan')
        )

    def is_enabled_in(self, chat):
        return chat.time_enabled

    async def handle_update(self, update: Update, context: CallbackContext = None):
        date_time_obj = datetime.datetime.now(fitz).strftime('%H:%M:%S.%f')[:-4]
        time_stamps_str = str(date_time_obj)
        reply_text = '\U0001F551 ' + time_stamps_str
        await update.effective_chat.send_message(reply_text)

import datetime

from telegram.ext import CallbackContext

from bot.command import ChatCommand
from bot import database
from telegram import Update

from bot.ranks import promote, demote
from bot.resources.bob_constants import fitz
from bot.utils_common import fitz_from


class LeetCommand(ChatCommand):
    def __init__(self):
        super().__init__(
            name='1337',
            regex=r'^1337$',  # Note! No command prefix
            help_text_short=('1337', 'Nopein ylenee')
        )

    def is_enabled_in(self, chat):
        return chat.leet_enabled

    async def handle_update(self, update: Update, context: CallbackContext = None):
        chat = database.get_chat(update.effective_chat.id)
        sender = database.get_chat_member(chat_id=update.effective_chat.id,
                                          tg_user_id=update.effective_user.id)
        # Message received datetime (determined by Telegram) in Finnish time zone
        msg_dt_fi_tz = fitz_from(update.effective_message.date) or datetime.datetime.now(fitz)
        if chat.latest_leet != msg_dt_fi_tz.date() and \
                msg_dt_fi_tz.hour == 13 and \
                msg_dt_fi_tz.minute == 37:
            chat.latest_leet = msg_dt_fi_tz.date()
            chat.save()
            reply_text = promote(sender)
        else:
            reply_text = demote(sender)
        await update.effective_chat.send_message(reply_text)

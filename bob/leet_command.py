from bob.abstract_command import AbstractCommand
import database
import datetime
import pytz
from telegram import Update
from ranks import promote, demote


class LeetCommand(AbstractCommand):
    def __init__(self):
        super().__init__(
            '1337',
            r'^1337$',
            ('1337', 'Nopein ylenee')
        )

    def handle_update(self, update):
        leet_command(update)

    def is_enabled_in(self, chat):
        return chat.leet_enabled


def leet_command(update: Update):
    now = datetime.datetime.now(pytz.timezone('Europe/Helsinki'))
    chat = database.get_chat(update.effective_chat.id)
    sender = database.get_chat_member(chat_id=update.effective_chat.id,
                                      tg_user_id=update.effective_user.id)
    if chat.latest_leet != now.date() and \
            now.hour == 13 and \
            now.minute == 37:
        chat.latest_leet = now.date()
        chat.save()
        reply_text = promote(sender)
    else:
        reply_text = demote(sender)
    update.message.reply_text(reply_text, quote=False)

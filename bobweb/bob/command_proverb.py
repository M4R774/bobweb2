from telegram import Update
from telegram.ext import CallbackContext, Updater

from bobweb.bob import database
from bobweb.bob.command import ChatCommand, regex_simple_command_with_parameters
from bobweb.bob.utils_common import auto_remove_msg_after_delay
from bobweb.web.bobapp.models import Proverb


class ProverbCommand(ChatCommand):
    def __init__(self):
        super().__init__(
            name='viisaus',
            regex=regex_simple_command_with_parameters('viisaus'),
            help_text_short=('!viisaus', 'Sananlaskuja yms.')
        )

    def handle_update(self, update: Update, context: CallbackContext = None):
        new_proverb = self.get_parameters(update.effective_message.text)

        if not new_proverb:
            update.effective_message.reply_text(
                "Anna uusi viisaus komennon jälkeen, esim. "
                "'.viisaus Aikainen lintu madon nappaa. 🦆'",
                quote=False)
        else:
            database.add_proverb(new_proverb, update.effective_user.id)
            acknowledgment_reply = update.effective_message.reply_text('Olemme taas hieman viisaampia. 🧠',
                                                                       quote=False)
            auto_remove_msg_after_delay(acknowledgment_reply, context, 10)

    def is_enabled_in(self, chat):
        return True  # Chat.proverb_enabled is checked in the scheduler.py. Adding new proverbs is enabled always.


async def broadcast_proverb(bot):
    chats_with_proverb_enabled = [chat for chat in database.get_chats() if chat.proverb_enabled]
    if len(chats_with_proverb_enabled) == 0:
        return
    for chat in chats_with_proverb_enabled:
        oldest_proverb = database.get_least_recently_seen_proverb_for_chat(chat.id)
        proverb_msg = create_proverb_message(oldest_proverb)
        bot.sendMessage(chat_id=chat.id, text=proverb_msg)


def create_proverb_message(proverb: Proverb):
    message = proverb.proverb
    message += " - " + str(proverb.tg_user)
    message += " " + str(proverb.date_created.strftime("%d.%m.%Y"))
    return message

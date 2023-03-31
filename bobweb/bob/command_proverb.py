from telegram import Update
from telegram.ext import CallbackContext

from bobweb.bob import database
from bobweb.bob.command import ChatCommand, regex_simple_command
from bobweb.bob.utils_common import auto_remove_msg_after_delay


class ProverbCommand(ChatCommand):
    def __init__(self):
        super().__init__(
            name='viisaus',
            regex=regex_simple_command('viisaus'),
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

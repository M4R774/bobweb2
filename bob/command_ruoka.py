import random

from telegram.ext import CallbackContext

from resources.recipes import recipes
from command import ChatCommand
from resources.bob_constants import PREFIXES_MATCHER
from telegram import Update


class RuokaCommand(ChatCommand):
    def __init__(self):
        super().__init__(
            name='ruoka',
            regex=r'^' + PREFIXES_MATCHER + r'ruoka($|\s)',
            help_text_short=('!ruoka', 'Ruokaresepti')
        )

    def handle_update(self, update: Update, context: CallbackContext = None):
        self.ruoka_command(update)

    def is_enabled_in(self, chat):
        return chat.ruoka_enabled

    def ruoka_command(self, update: Update) -> None:
        """
        Send a message when the command /ruoka is issued.
        Returns link to page in https://www.soppa365.fi
        """
        parameter = self.get_parameters(update.message.text)

        recipes_with_parameter_text = [r for r in recipes if parameter in r.replace('-', ' ')]

        if len(recipes_with_parameter_text) > 0:
            reply_text = random.choice(recipes_with_parameter_text)
        else:
            reply_text = random.choice(recipes)

        update.message.reply_text(reply_text, quote=False)


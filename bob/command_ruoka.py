import random

from telegram.ext import CallbackContext

from command import ChatCommand
from bob.resources.bob_constants import PREFIXES_MATCHER
from telegram import Update


class RuokaCommand(ChatCommand):
    def __init__(self):
        super().__init__(
            name='ruoka',
            regex=r'' + PREFIXES_MATCHER + 'ruoka',
            help_text_short=('!ruoka', 'Ruokaresepti')
        )

    def handle_update(self, update: Update, context: CallbackContext = None):
        ruoka_command(update)

    def is_enabled_in(self, chat):
        return chat.ruoka_enabled


def ruoka_command(update: Update) -> None:
    """
    Send a message when the command /ruoka is issued.
    Returns link to page in https://www.soppa365.fi
    """
    with open("resources/recipes.txt", "r") as recipe_file:
        recipes = recipe_file.readlines()

    reply_text = random.choice(recipes)

    update.message.reply_text(reply_text, quote=False)


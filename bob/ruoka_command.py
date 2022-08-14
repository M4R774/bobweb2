import random

from abstract_command import AbstractCommand
from bob.constants import PREFIXES_MATCHER
from telegram import Update


class RuokaCommand(AbstractCommand):
    def __init__(self):
        super().__init__(
            'ruoka',
            r'' + PREFIXES_MATCHER + 'ruoka',
            ('!ruoka', 'Ruokaresepti')
        )

    def handle_update(self, update):
        ruoka_command(update)

    def is_enabled_in(self, chat):
        return chat.ruoka_enabled


def ruoka_command(update: Update) -> None:
    """
    Send a message when the command /ruoka is issued.
    Returns link to page in https://www.soppa365.fi
    """
    with open("recipes.txt", "r") as recipe_file:
        recipes = recipe_file.readlines()

    reply_text = random.choice(recipes)

    update.message.reply_text(reply_text, quote=False)


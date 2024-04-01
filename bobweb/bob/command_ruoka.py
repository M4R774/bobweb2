import random

from telegram.ext import CallbackContext

from bobweb.bob.message_board import ScheduledMessage
from bobweb.bob.resources.recipes import recipes
from bobweb.bob.command import ChatCommand, regex_simple_command_with_parameters
from telegram import Update


class RuokaCommand(ChatCommand):
    def __init__(self):
        super().__init__(
            name='ruoka',
            regex=regex_simple_command_with_parameters('ruoka'),
            help_text_short=('!ruoka', 'Ruokaresepti')
        )

    def is_enabled_in(self, chat):
        return chat.ruoka_enabled

    async def handle_update(self, update: Update, context: CallbackContext = None):
        """
        Send a message when the command /ruoka is issued.
        Returns link to page in https://www.soppa365.fi
        """
        parameter = self.get_parameters(update.effective_message.text)

        recipes_with_parameter_text = [r for r in recipes if parameter in r.replace('-', ' ')]

        if len(recipes_with_parameter_text) > 0:
            reply_text = random.choice(recipes_with_parameter_text)  # NOSONAR
        else:
            reply_text = random.choice(recipes)  # NOSONAR

        await update.effective_chat.send_message(reply_text)


def create_message_board_daily_message(chat_id: int = None) -> ScheduledMessage:
    recipe_link = random.choice(recipes)  # NOSONAR
    # Find name link by extracting last part of link after '/' and replacing dashes with spaces
    recipe_name = recipe_link.split('/')[-1].replace('-', ' ')
    # Try to find additional details of the recipe

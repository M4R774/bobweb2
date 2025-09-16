import logging

from telegram import Update
from telegram.ext import CallbackContext

from bot.commands.base_command import BaseCommand, regex_simple_command_with_parameters

logger = logging.getLogger(__name__)


class KuntaCommand(BaseCommand):
    """ Municipality command ('Kunta') function has been removed. Now if the command is given bot just informs that
        the functionality is no longer available."""
    def __init__(self):
        super().__init__(
            name='kunta',
            regex=regex_simple_command_with_parameters('kunta'),
            help_text_short=('!kunta', 'Satunnainen kunta')
        )

    _functionality_has_been_removed_info = '🤖 Kunta-toiminto on valitettavasti poistettu käytöstä 🤖'

    def is_enabled_in(self, chat):
        return True

    async def handle_update(self, update: Update, context: CallbackContext = None):
        await update.effective_chat.send_message(self._functionality_has_been_removed_info)

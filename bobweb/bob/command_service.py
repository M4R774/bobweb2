import json
import logging
from typing import List, Optional

from telegram import Update, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import CallbackContext

from bobweb.bob.command import ChatCommand

from bobweb.bob.command_kunta import KuntaCommand

from bobweb.bob.utils_common import has


logger = logging.getLogger(__name__)


# Command Service that creates and stores all commands on initialization and all active CommandActivities
# is initialized below on first module import. To get instance, import it from below
class CommandService:
    commands: List[ChatCommand] = []

    def __init__(self):
        self.create_command_objects()

    async def reply_and_callback_query_handler(self, update: Update, context: CallbackContext = None) -> bool:
        """
        Handler for reply and callback query updates.
        :param update:
        :param context:
        :return: True, if update was handled by this handler. False otherwise.
        """
        if has(update.callback_query):
            target = update.effective_message
        else:
            target = update.effective_message.reply_to_message

        target_activity = self.get_activity_by_message_and_chat_id(target.message_id, target.chat_id)

        if target_activity is not None:
            await target_activity.delegate_response(update, context)
            return True
        elif has(update.callback_query):
            # If has a callback query, it means that the update is a inline keyboard button press.
            # As the ChatActivity state is no longer persisted in the command_service instance, we'll update
            # content of the message that had the pressed button.
            edited_text = 'Toimenpide aikakatkaistu ⌛️ Aloita se uudelleen uudella komennolla.'
            if target.text:
                edited_text = f'{target.text}\n\n{edited_text}'
            await target.edit_text(edited_text, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup([]))
            return True
        else:
            return False

    def create_command_objects(self):
        # 1. Define all commands (except help, as it is dependent on the others)
        # 2. Return list of all commands with helpCommand added
        commands_without_help = self.create_all_but_help_command()
        # Ip-address command is added after HelpCommand is created as
        # it is restricted only to project maintainers
        self.commands = commands_without_help

    def create_all_but_help_command(self) -> List[ChatCommand]:
        return [
            KuntaCommand(),
        ]


#
# singleton instance of command service
#
instance = CommandService()

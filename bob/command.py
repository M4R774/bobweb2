import re
import string

from telegram import Update
from telegram.ext import CallbackContext


# Base class for creating commands.
# To add a new command, create a concrete implementation that extends this class and add its constructor call to
# command_service.create_all_but_help_command.
#
# Attributes:
# - name -> Name of the command.
# - regex -> regex matcher to use for determining if message contains this command
# - help -> tuple
#   - [0]: short name with possible command prefix
#   - [1]: short description of the command
#   - Help text is used by HelpCommand to list available commands in chat

class ChatCommand:

    # Attributes that all Commands Should have
    def __init__(self, name, regex, help_text_short):
        self.name: string = name
        self.regex: regex = regex
        self.help_text_short: tuple[string, string] = help_text_short

    def handle_update(self, update: Update, context: CallbackContext = None) -> None:
        raise NotImplementedError

    def is_enabled_in(self, chat) -> bool:
        raise NotImplementedError

    def regex_matches(self, message) -> bool:
        return re.search(self.regex, message) is not None

    # Everything after command regex match with whitespaces stripped
    def get_parameters(self, text: string) -> string:
        return ''.join(re.split(self.regex, text)).strip()

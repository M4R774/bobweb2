import os
import re
import string
from typing import TypeVar

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
import django

from bobweb.bob.resources.bob_constants import PREFIXES_MATCHER

os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    "bobweb.web.web.settings"
)
os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"
django.setup()
from bobweb.web.bobapp.models import Chat


class ChatCommand:
    # Determines if the command's handler should be invoked on message edit or on replies.
    # By default, set to false
    invoke_on_edit = False
    invoke_on_reply = False

    # If command should be handled asynchronously in a new thread
    # NOTE: Only commands that do not use shared resources (including database) can be run async without more robust
    # system (transactions and ACID principles)
    run_async = False

    # Attributes that all Commands Should have
    def __init__(self, name, regex, help_text_short):
        self.name: string = name
        self.regex: regex = regex
        self.help_text_short: tuple[string, string] = help_text_short

    def handle_update(self, update: Update, context: CallbackContext = None) -> None:
        raise NotImplementedError

    def is_enabled_in(self, _: Chat) -> bool:
        return True

    def regex_matches(self, message: string) -> bool:
        return re.search(self.regex, message) is not None

    # Everything after command regex match with whitespaces stripped
    def get_parameters(self, text: string) -> string:
        return ''.join(re.split(self.regex, text)).strip()


# Static ChatCommand class type for any type checking
chat_command_class_type = TypeVar('chat_command_class_type', bound=ChatCommand)


def regex_simple_command(command_str: str):
    """
    Returns a str type regex matcher for command. triggers if message
    _only contains_ given command with prefix (case-insensitive)

    regex:
    - (?i) = case insensitive flag
    - ^ = from the start of the string
    - [./!] = any character defined in brackets
    - $ = end of the string

    :param command_str: command without prefix
    :return: str regex matcher that detects if message contains given command
    """
    return rf'(?i)^{PREFIXES_MATCHER}{command_str}$'


def regex_command_with_parameters(command_str: str):
    """
    Returns a str type regex matcher for command. triggers if message
    _starts with_ given command with prefix (case-insensitive)

    regex:
    - check 'regex_match_case_insensitive_with_prefix_only_command'
    - ($|\s) = either end of string or white space without end of string

    :param command_str: command without prefix
    :return: str regex matcher that detects if message contains given command
    """
    return rf'(?i)^{PREFIXES_MATCHER}{command_str}($|\s)'

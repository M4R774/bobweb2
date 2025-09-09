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

from bot.resources.bob_constants import PREFIXES_MATCHER

os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    "web.settings"
)
os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"
django.setup()
from web.bobapp.models import Chat


class ChatCommand:
    # Determines if the command's handler should be invoked on message edit or on replies.
    # By default, set to false
    invoke_on_edit = False
    invoke_on_reply = False

    # Attributes that all Commands Should have
    def __init__(self, name, regex, help_text_short):
        self.name: string = name
        self.regex: regex = regex
        self.help_text_short: tuple[str, str] = help_text_short

    def is_enabled_in(self, _: Chat) -> bool:
        return True

    async def handle_update(self, update: Update, context: CallbackContext = None) -> None:
        raise NotImplementedError

    def regex_matches(self, message: str) -> bool:
        return re.search(self.regex, message) is not None

    def get_parameters(self, text: str) -> str:
        """
        :param text: message text
        :return: All text after command regex match with leading and trailing white space trimmed
        """
        return get_content_after_regex_match(text, self.regex)


def get_content_after_regex_match(text: str, regex: str) -> str | None:
    """ static version of get_parameters
        :return: None if either parameter is None. Otherwise, str after mached regex"""
    if text is None or regex is None:
        return None
    groups = [group for group in re.split(regex, text) if group is not None]
    return ''.join(groups).strip()


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
    command_str_matcher = command_str_with_nordics_or_non_nordic_chars(command_str)
    return rf'(?i)^{PREFIXES_MATCHER}{command_str_matcher}$'


def regex_simple_command_with_parameters(command_str: str, command_prefix_is_optional: bool = False):
    """
    Returns a str type regex matcher for command. triggers if message
    _starts with_ given command with prefix (case-insensitive)

    regex:
    - check 'regex_match_case_insensitive_with_prefix_only_command'
    - ($|\s) = either end of string or white space without end of string

    :param command_str: command without prefix
    :param command_prefix_is_optional: true, if command prefix is optional
    :return: str regex matcher that detects if message contains given command
    """
    command_prefix_matcher = PREFIXES_MATCHER + ('?' if command_prefix_is_optional else '')
    command_str_matcher = command_str_with_nordics_or_non_nordic_chars(command_str)
    return rf'(?i)^{command_prefix_matcher}{command_str_matcher}($|\s)'


def command_str_with_nordics_or_non_nordic_chars(command_str: str):
    """
    Returns regex matcher for the command string where any instance of
        - 'å' is matched with either 'å' or 'a'
        - 'ä' is matched with either 'ä' or 'a'
        - 'ö' is matched with either 'ö' or 'o'
    :param command_str: command string
    :return: matcher, where either nordic character or it's ascii counterpart is accepted
    """
    return command_str.replace('ä', '[aä]').replace('ö', '[oö]').replace('å', '[aå]')

import string

from telegram import Update
from telegram.ext import CallbackContext
from typing import List

from bobweb.bob.utils_format import MessageArrayFormatter, Align
from bobweb.bob.resources.bob_constants import PREFIXES_MATCHER
from bobweb.bob.command import ChatCommand


class HelpCommand(ChatCommand):
    def __init__(self, other_commands):
        super().__init__(
            name='help',
            regex=r'^' + PREFIXES_MATCHER + 'help$',
            help_text_short=None
        )
        # Help text is formatted once and stored as attribute
        self.reply_text = create_reply_text(other_commands)

    def handle_update(self, update: Update, context: CallbackContext = None):
        update.message.reply_text(self.reply_text, parse_mode='Markdown', quote=False)

    def is_enabled_in(self, chat):
        return True


def create_reply_text(commands: List[ChatCommand]) -> string:
    headings = ['Komento', 'Selite']
    command_array = create_command_array(commands)
    command_array.insert(0, headings)

    formatter = MessageArrayFormatter('|', '-').with_truncation(28, 1).with_column_align([Align.LEFT, Align.LEFT])
    formatted_arr = formatter.format(command_array)

    footer = 'Etumerkillä aloitetut komennot voi aloitta joko huutomerkillä, pisteellä tai etukenolla [!./].'

    return '```\n' \
           + 'Bob-botti osaa auttaa ainakin seuraavasti:\n\n' \
           + f'{formatted_arr}\n' \
           + f'{footer}\n' \
           + '```'


def create_command_array(commands: List[ChatCommand]):
    array_of_commands = []
    for command in commands:
        if command.help_text_short is not None:
            command_row = [command.help_text_short[0], command.help_text_short[1]]
            array_of_commands.append(command_row)
    return array_of_commands

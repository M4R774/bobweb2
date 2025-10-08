import string

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import CallbackContext
from typing import List

from bot.utils_format import MessageArrayFormatter, Align
from bot.commands.base_command import BaseCommand, regex_simple_command

class HelpCommand(BaseCommand):
    def __init__(self, other_commands):
        super().__init__(
            name='help',
            regex=regex_simple_command('help'),
            help_text_short=None
        )
        # Help text is formatted once and stored as attribute
        self.reply_text = create_reply_text(other_commands)

    async def handle_update(self, update: Update, context: CallbackContext = None):
        await update.effective_chat.send_message(self.reply_text, parse_mode=ParseMode.MARKDOWN)


def create_reply_text(commands: List[BaseCommand]) -> string:
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


def create_command_array(commands: List[BaseCommand]):
    array_of_commands = []
    for command in commands:
        if command.help_text_short is not None:
            command_row = [command.help_text_short[0], command.help_text_short[1]]
            array_of_commands.append(command_row)
    return array_of_commands

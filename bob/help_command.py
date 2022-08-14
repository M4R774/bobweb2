from bob.constants import PREFIXES_MATCHER
from bob.abstract_command import AbstractCommand


class HelpCommand(AbstractCommand):
    def __init__(self, other_commands):
        name = 'help_text',
        regex = r'' + PREFIXES_MATCHER + 'help'
        help_text = ''

        super().__init__(name, regex, help_text)
        self.other_commands = other_commands
        self.longest_name_length = get_longest_command_help_text_name_length(other_commands)

    def handle_update(self, update):
        help_command(update, self.other_commands, self.longest_name_length)

    def is_enabled_in(self, chat):
        return True


# Longest command help text calculated once per and passed to help_command as argument
def get_longest_command_help_text_name_length(commands):
    return max([len(command.help_text_short[0]) for command in commands if command.help_text_short is not None])


def help_command(update, commands, longest_name_length):
    command_heading = form_command_with_tab('Komento', longest_name_length) + 'Selite'
    command_string_list = form_command_help_list(longest_name_length, commands)

    reply_text = "```\nBob-botti osaa auttaa ainakin seuraavasti:\n\n" \
                 + command_heading + \
                 "\n--------------------------------------\n" \
                 + command_string_list + \
                 "\nEtumerkillä aloitetut komennot voi aloitta joko huutomerkillä, pisteellä tai etukenolla [!./].\n```"
    update.message.reply_text(reply_text, parse_mode='Markdown', quote=False)


def form_command_with_tab(text, longest_command_length):
    return text + ' ' * (longest_command_length - len(text)) + ' | '


def form_command_help_list(max_length, commands):
    output_text = ''
    for command in commands:
        if command.help_text_short is not None:
            command_text = form_command_with_tab(command.help_text_short[0], max_length)
            description = command.help_text_short[1]
            output_text += command_text + description + '\n'
    return output_text

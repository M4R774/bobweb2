from constants import HELP_TEXT


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


def form_command_help_list(maxlen, commands):
    output_text = ''
    for key in commands:
        if HELP_TEXT in commands[key]:
            command_text = form_command_with_tab((commands[key][HELP_TEXT])[0], maxlen)
            description = (commands[key][HELP_TEXT])[1]
            output_text += command_text + description + '\n'
    return output_text

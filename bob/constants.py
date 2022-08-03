HANDLER = 'handler'  # method: receives the message that contained the command
ENABLER = 'enabler'  # method: defines if command is enabled
REGEX = 'regex'  # regex: custom regex to match the command. If empty, strict match to command name
HELP_TEXT = 'help_text'  # tuple: [0]: name [1]: description
COMMAND_PREFIXES = ['.', '/', '!']  # List of supported prefixes
PREFIXES_MATCHER = '[{}]'.format(''.join(COMMAND_PREFIXES))  # prefixes as regex matcher

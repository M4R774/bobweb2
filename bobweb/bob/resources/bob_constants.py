COMMAND_PREFIXES = ['.', '/', '!']  # List of supported prefixes
PREFIXES_MATCHER = '[{}]'.format(''.join(COMMAND_PREFIXES))  # prefixes as regex matcher
FINNISH_DATE_FORMAT = '%d.%m.%Y'  # Standard Finnish date format
ISO_DATE_FORMAT = '%Y-%m-%d'  # Standard ISO 8601 date format
EXCEL_DATETIME_FORMAT = '%Y-%m-%d %H:%M:%S'  # Best format for excel
DEFAULT_TIMEZONE = 'Europe/Helsinki'  # Default timezone for bot
BOT_USERNAME = "BandOfBrothersBot"

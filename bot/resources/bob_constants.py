from zoneinfo import ZoneInfo

# Prefixes used by commands
COMMAND_PREFIXES = ['.', '/', '!']  # List of supported prefixes
PREFIXES_MATCHER = '[{}]'.format(''.join(COMMAND_PREFIXES))  # prefixes as regex matcher

# Standard date and time formats
DEFAULT_TIME_FORMAT = '%H:%M'  # Default time format
FINNISH_DATE_FORMAT = '%d.%m.%Y'  # Standard Finnish date format
FINNISH_DATE_TIME_FORMAT = '%d.%m.%Y %H:%M'  # Standard Finnish date with time format
ISO_DATE_FORMAT = '%Y-%m-%d'  # Standard ISO 8601 date format
EXCEL_DATETIME_FORMAT = '%Y-%m-%d %H:%M:%S'  # Best format for excel
FILE_NAME_DATE_FORMAT = '%Y-%m-%d_%H%M'  # For files. Contains no illegal characters

# Apps Hungarian notation is used to embed timezone information to variables and methods
# to prevent simple mistakes of
FINNISH_TIMEZONE_NAME = 'Europe/Helsinki'  # Default timezone for bot
FINNISH_TZ = ZoneInfo(FINNISH_TIMEZONE_NAME)

# Single telegram text message max content length in characters
TELEGRAM_MESSAGE_MAX_LENGTH = 4096
# Maximum character count for caption in message with media (photo, video etc.)
TELEGRAM_MEDIA_MESSAGE_CAPTION_MAX_LENGTH = 1024

import asyncio
import contextlib
import inspect
import logging
from datetime import datetime, timedelta, date
from decimal import Decimal
from functools import wraps
from typing import List, Sized, Tuple, Optional, Type, Callable

import pytz
import telegram
from django.db.models import QuerySet
from telegram import Message, Update, Chat
from telegram.constants import ChatAction, ParseMode
from telegram.ext import CallbackContext
from xlsxwriter.utility import datetime_to_excel_datetime

from bobweb.bob.resources.bob_constants import FINNISH_DATE_FORMAT, fitz, TELEGRAM_MESSAGE_MAX_LENGTH

logger = logging.getLogger(__name__)


async def auto_remove_msg_after_delay(msg: Message, context: CallbackContext, delay=5.0):
    async def implementation():
        await asyncio.sleep(delay)
        await remove_msg(msg, context)
    asyncio.get_running_loop().create_task(implementation())


async def remove_msg(msg: Message, context: CallbackContext) -> None:
    if context is not None:
        await context.bot.delete_message(chat_id=msg.chat_id, message_id=msg.message_id)


async def send_bot_is_typing_status_update(chat: Chat):
    """ Sends status update that adds 'Bot is typing...' text to the top of
        the active chat in users' clients. Should be only used, when there
        is a noticeable delay before next update. """
    await chat.send_chat_action(action=ChatAction.TYPING)


def has(obj) -> bool:
    if obj is None:
        return False

    if isinstance(obj, str):
        return obj is not None
    if isinstance(obj, QuerySet):
        return obj.count() > 0
    if isinstance(obj, Sized):
        return len(obj) > 0
    if hasattr(obj, "__len__"):
        return obj.__len__ > 0

    return True  # is not any above and is not None


def has_no(obj: object) -> bool:
    if obj is None:
        return True
    if isinstance(obj, QuerySet):
        return obj.count() == 0
    if hasattr(obj, "__len__"):
        return obj.__len__ == 0
    return False  # should have length 0 or be None


def find_first_not_none(iterable: List[any]) -> Optional[any]:
    """
    Returns first item in iterable that is not None. If no item is not None, returns None.
    """
    for item in iterable:
        if item is not None:
            return item
    return None


def flatten(item: any) -> List:
    if not item:  # Empty list or None
        return item
    if isinstance(item[0], list) or isinstance(item[0], tuple):
        return flatten(item[0]) + flatten(item[1:])
    return item[:1] + flatten(item[1:])


def split_to_chunks(sized_obj: Optional[Sized], chunk_size: int) -> List:
    """
    Splits given sized object into chunks of given size
    :param sized_obj: any object that is Sized
    :param chunk_size: positive integer. If None or 0, returns empty list
    :return: list with the chunks
    """
    if not sized_obj or not chunk_size or chunk_size <= 0:
        return []
    list_of_chunks = []
    for i in range(0, len(sized_obj), chunk_size):
        list_of_chunks.append(sized_obj[i:i + chunk_size])
    return list_of_chunks


async def reply_long_text_with_markdown(update: Update,
                                        text: str,
                                        do_quote: bool = False,
                                        min_msg_length: int = 1024,
                                        max_msg_length: int = TELEGRAM_MESSAGE_MAX_LENGTH):
    """
    Wrapper for Python Telegram Bot API's Message#reply_text that can handle
    long replies that contain messages with content length near or over Telegram's
    message content limit of 1024/4096 characters. If text is near the limit it is
    split into multiple messages that are decorated with number of current message
    and number of total messages. For example "[message content]... (1 / 2)".

    This function tries to keep text block elements in the same message (paragraphs
    and code blocks). Sends message using PTB ParseMode.MARKDOWN.
    """
    if len(text) <= max_msg_length:
        return await update.effective_message.reply_text(text, do_quote=do_quote, parse_mode=ParseMode.MARKDOWN)

    # Total maximum message length is reduced by 20 characters to leave room for the footer of the message.
    chunks = split_text_keep_text_blocks(text, min_msg_length, max_msg_length - 10)
    chunk_count = len(chunks)
    # Each sent message is sent as reply to the previous message so that reply chains are kept intact
    previous_message: Optional[Message] = None
    for i, chunk in enumerate(chunks):
        msg = chunk + f'\n({i + 1}/{chunk_count})'
        if i == 0:
            previous_message = await update.effective_message.reply_text(
                msg, do_quote=do_quote, parse_mode=ParseMode.MARKDOWN)
        elif previous_message:
            # After first message, bot replies to its own previous message. do_quote=True => is sent as reply
            previous_message = await previous_message.reply_text(msg, do_quote=True, parse_mode=ParseMode.MARKDOWN)


def split_text_keep_text_blocks(text: str, min_msg_characters: int, max_msg_characters: int):
    """
    Splits given text to list of text chunks. Tries not to split a code block or a paragraph to
    different messages. Splits at last fitting boundary inside the given character index range
    for each message. If no fitting boundary is found inside the range, does a hard cut at the
    range end. If there is a code block open at the range end, adds ending markdown and starts next
    message with a code block. Priority of boundaries is as follows:
    1. Last paragraph change if not inside code block
    2. Last code block start if range end is inside the code block
    3. Hard split inside code block or paragraph if there is no fitting boundary inside the split range
    Note: In Markdown code blocks cannot be nested.
    :param text: any text
    :param min_msg_characters: soft limit starting from which text can be split
    :param max_msg_characters: hard limit for splitting the text. If no boundary is found between
                       soft and hard limits, text is split at the hard limit.
    :return: list of text chunks
    """
    code_block_boundary = '```'
    double_line_change = '\n\n'
    code_block_start_tag = '```\n'
    code_block_end_tag = '\n```'
    chunks = []

    while text and text != '':
        if len(text) <= max_msg_characters:
            chunks.append(text)
            return chunks

        # Etitään kaikki saulat / rajat
        all_code_block_boundary_indexes = [i for i in find_start_indexes(text, code_block_boundary)]

        # Tän jälkeen etsitään ensimmäinen, jonka indeksi on suurempi kuin limitti
        next_code_block_boundary_after_limit = None
        for b_index, character_index_in_text in enumerate(all_code_block_boundary_indexes):
            if character_index_in_text >= max_msg_characters:
                next_code_block_boundary_after_limit = b_index
                break

        # If next code block boundary after limit exists and it is even (closing boundary, +1 for 0-starting indexing),
        # it means that the limit is inside the code block
        if next_code_block_boundary_after_limit and (next_code_block_boundary_after_limit + 1) % 2 == 0:
            # If next boundary over the limit is a closing code block, this means that the limit is inside the code
            # block. In this case, we split before that code block if it's start is before the split range start
            previous_boundary = all_code_block_boundary_indexes[next_code_block_boundary_after_limit - 1]
            if previous_boundary > min_msg_characters:
                chunks.append(text[:previous_boundary].strip())
                text = text[previous_boundary:].strip()
            else:
                # Previous boundary is before the split range start. We split the code block at the last double
                # line change. Find last line change inside the limit (-4 so that ending code block can be added)
                line_changes = [i for i in find_start_indexes(text, double_line_change)
                                if min_msg_characters < i < max_msg_characters - len(code_block_end_tag)]
                split_index = line_changes[-1] \
                    if line_changes and line_changes[-1] > len(code_block_start_tag) else max_msg_characters
                chunks.append(text[:split_index] + code_block_end_tag)
                text = code_block_start_tag + text[split_index:].strip()
        else:
            # Either no closing code block boundaries over the limit or no code block boundaries at all.
            # Split at last paragraph
            paragraph_boundaries_before_limit = [i for i in find_start_indexes(text, double_line_change)
                                                 if min_msg_characters < i < max_msg_characters]
            if paragraph_boundaries_before_limit:
                split_index = paragraph_boundaries_before_limit[-1]
                chunks.append(text[:split_index])
                text = text[split_index:].strip()
                continue
            # As last cause, split at last white space character before the limit

            i = max_msg_characters - 1
            while i >= min_msg_characters - 1:
                if text[i].isspace():
                    chunks.append(text[:i])
                    text = text[i:].strip()
                    break
                i -= 1
            # Case where there is no white space character before the limit
            if i < min_msg_characters - 1:
                split_index = max_msg_characters
                chunks.append(text[:split_index])
                text = text[split_index:].strip()
    return chunks


def find_start_indexes(text, search_string):
    """
    Find the start of all (possibly-overlapping) instances of needle in haystack
    """
    offs = -1
    while True:
        offs = text.find(search_string, offs+1)
        if offs == -1:
            break
        else:
            yield offs


class MessageBuilder:
    """
    For building messages by appending new text
    """
    def __init__(self, message: str = None):
        self.message = message or ''

    def append_to_new_line(self, item: any, prefix: str = None, postfix: str = None) -> 'MessageBuilder':
        """
        Appends given text to the message to a new line if given text is not None or empty string.
        Returns self, so that calls can be chained. Prefix and postfix are optional and nothing is added
        if given item value is None or an empty string.
        """
        if item is not None and str(item) != '':
            self.message += '\n' + (prefix or '') + str(item) + (postfix or '')
        return self

    def append_raw(self, item: any) -> 'MessageBuilder':
        """
        Appends given text without any checks. Returns self, so that calls can be chained.
        """
        self.message += str(item)
        return self


def min_max_normalize(value_or_iterable: Decimal | int | List[Decimal | int] | List[List],
                      old_min=0,
                      old_max=1,
                      new_min=0,
                      new_max=1) -> Decimal | List[Decimal] | List[List]:
    """
    Applies min max normalization to list of numeric values or list of lists that contain numeric values
    :param value_or_iterable: single value, list of values or list of lists of values
    :param old_min: min value for the old scale
    :param old_max: max value for the old scale
    :param new_min: new minimum value
    :param new_max: new maximum value
    :return:
    """

    def normalization_function(x) -> Decimal:
        return Decimal((x - old_min) * (new_max - new_min)) / Decimal((old_max - old_min)) + new_min

    # If given value_or_iterable is single value, return it as normalized
    if isinstance(value_or_iterable, int) or isinstance(value_or_iterable, Decimal):
        return normalization_function(value_or_iterable)

    # If given value is list, Scale each value to be within the new range
    scaled_values = []
    for value in value_or_iterable:
        if isinstance(value, list):
            # If value is instance of list do recursive call
            scaled_val = min_max_normalize(value, old_min, old_max, new_min, new_max)
        else:
            scaled_val = normalization_function(value)
        scaled_values.append(scaled_val)

    return scaled_values


def object_search(data: dict | object, *args, default: any = None):
    """
    Tries to get value from a nested object using a list of keys/indices.
    Iterates through given keys / indices and for each string parameter
    tries to get attr with same name progress to a node with that name.
    For each index is assumed that current node is an array or tuple and
    tries to progress to a node in given index. If no error is raised
    by the traversal, returns last node.

    Note! To get detailed information why None was returned, set
    logging level to DEBUG

    :param data: the object to search
    :param args: a list of keys/indices to traverse the object. If none
                 or empty, given data is returned as is
    :param default: any value. Is returned instead of None if object_search does
                    not find item from given path or exception is raised from
                    the search
    :return: the value in the nested dictionary or None if any exception occurs
    """
    traversed_path = ''

    try:
        for arg in args:
            if isinstance(arg, str):
                data, traversed_path = __dict_search_handle_str_arg(data, traversed_path, arg)
            elif isinstance(arg, int):
                data, traversed_path = __dict_search_handle_int_arg(data, traversed_path, arg)
            else:
                raise TypeError(f"Expected arguments to be of any type [str|int] "
                                f"but got {type(arg).__name__}")
        # Node in the last given specification
        return data
    except (KeyError, TypeError, IndexError, AttributeError) as e:  # handle exceptions and return None
        traversed_text = __dict_search_get_traversed_path_text(traversed_path)
        caller: inspect.FrameInfo = get_caller_from_stack()
        debug_msg = f"Error searching value from object: {e}. " + \
                    f"{traversed_text}. [module]: {inspect.getmodule(caller[0]).__name__}" + \
                    f" [function]: {str(caller.function)}, [row]: {str(caller.lineno)}, [*args content]: {str(args)}"
        logger.debug(debug_msg)

        return default  # given call parameter or default None


def __dict_search_handle_str_arg(data: dict, traversed_path, str_arg: str) -> Tuple[dict, str]:
    if isinstance(data, list) or isinstance(data, tuple):
        raise TypeError(f"Expected object or dict but got "
                        f"{type(data).__name__}")

    if not isinstance(data, dict):
        return getattr(data, str_arg), traversed_path + f'[\'{str_arg}\']'

    return data[str_arg], traversed_path + f'[\'{str_arg}\']'


def __dict_search_handle_int_arg(data: dict, traversed_path, int_arg: int) -> Tuple[dict, str]:
    if not isinstance(data, list) and not isinstance(data, tuple):
        raise TypeError(f"Expected list or tuple but got "
                        f"{type(data).__name__}")
    return data[int_arg], traversed_path + f'[{int_arg}]'


def __dict_search_get_traversed_path_text(traversed_path: str) -> str:
    if traversed_path == '':
        return 'Error raised from dict root, no traversal done'
    else:
        return f'Path traversed before error: {traversed_path}'


def get_caller_from_stack(stack_depth: int = 1) -> inspect.FrameInfo | None:
    """
    Note! The caller this function name is referencing is not caller of this function, but caller
    of the function that is calling this function!

    Returns FrameInfo of the function that was called in the stack n (called_depth)
    calls before this function call.

    Example:

    def main():
        do_stuff()

    def do_stuff():
        get_caller_from_stack()  # should return FrameInfo of function 'main' as it called 'do_stuff'

    :param stack_depth: how many levels up in the call stack to look
           - 0: caller of this 'get_caller_from_stack' function (effectively returns function name
                from where this was called)
           - 1: caller of the function that called this 'get_caller_from_stack'
           - n: caller at given index of the call stack filtered by package_level_filter. If n
                is bigger than the call stack, last item is returned
    :return: FrameInfo of the function in the given position of the filtered call stack
    """
    # get the current frame and the stack
    frame = inspect.currentframe()
    stack = inspect.getouterframes(frame)

    current_depth = 0
    # iterate over the stack until we find a function that is in the package level scope and call depth
    for i in range(0, len(stack)):
        frame = stack[i][0]
        module = inspect.getmodule(frame)
        if module is None:
            continue
        if current_depth == stack_depth + 1:
            return stack[i]
        else:
            current_depth += 1

    # if we reach the end of the stack without finding a caller, return None
    return None


class HandleException:
    """
    Decorator for exception handling. Catches the exception if it is of given expected type. If not, the exception is
    not caught and instead is passed on in the stack. Returns given return value to the caller of the wrapped function.
    If log message is given, the exception is logged. Otherwise, it is handled silently.

    Supports both async and sync functions while used as function decorator.
    :param exception_type: exception type that is expected
    :param return_value: return value in case of the exception
    :param log_msg: optional message
    :param exception_filter: catch and handle exception only if this filter returns true (predicate for the exception)
    :return: decorator that handles exception as specified
    """
    def __init__(self,
                 exception_type: Type[Exception],
                 return_value: any = None,
                 log_msg: Optional[str] = None,
                 log_level: int = logging.ERROR,
                 exception_filter: Callable[[Exception], bool] | None = None):
        self._exception_type = exception_type
        self._return_value = return_value
        self._log_msg = log_msg
        self._log_level = log_level
        self._exception_filter = exception_filter

    #
    # For using as function wrapper
    #
    def __call__(self, func):
        if asyncio.iscoroutinefunction(func):
            @wraps(func)
            async def wrapped_func(*args, **kwargs):
                try:
                    return await func(*args, **kwargs)
                except self._exception_type as e:
                    return self.__process_caught_exception(e)
            return wrapped_func
        else:
            @wraps(func)
            def wrapped_func(*args, **kwargs):
                try:
                    return func(*args, **kwargs)
                except self._exception_type as e:
                    return self.__process_caught_exception(e)
            return wrapped_func

    def __process_caught_exception(self, exception: Exception):
        # Processes exception.
        # - If it does not pass exception filter, it is raised again.
        # - If _log_msg is defined, it is logged.
        # - Returns defined _return_value or None if not defined
        if self._exception_filter and self._exception_filter(exception) is False:
            raise exception  # NOSONAR
        if self._log_msg:
            logger.log(level=self._log_level, msg=self._log_msg, exc_info=exception)
        return self._return_value

    #
    # For using as context manager
    #
    def __enter__(self):
        return self

    async def __aenter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if isinstance(exc_val, self._exception_type):
            if self._exception_filter and self._exception_filter(exc_val) is False:
                return False  # Propagate the exception
            if self._log_msg:
                logger.log(level=self._log_level, msg=self._log_msg, exc_info=exc_val)
            return True  # Suppress the exception
        return False  # Propagate the exception if it's not the expected type

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self.__exit__(exc_type, exc_val, exc_tb)


# Only for more familiar camel case naming
def handle_exception(exception_type: Type[Exception],
                     return_value: any = None,
                     log_msg: str | None = None,
                     log_level: int = logging.ERROR,
                     exception_filter: Callable[[Exception], bool] | None = None):
    return HandleException(exception_type, return_value, log_msg, log_level, exception_filter)


#
# Wrappers to be used with PTB (Python Telegram Bot Library) API-calls
#
def ignore_message_not_found_telegram_error():
    return HandleException(telegram.error.BadRequest, exception_filter=lambda e: 'not found' in e.message.lower())


def utctz_from(dt: datetime) -> Optional[datetime]:
    """ UTC TimeZone converted datetime from given datetime. If naive datetime is given, it is assumed
        to be in utc timezone already """
    if dt is None:
        return None
    if dt.tzinfo is None:
        return pytz.UTC.localize(dt)
    return dt.astimezone(pytz.UTC)


def fitz_from(dt: datetime) -> Optional[datetime]:
    """ Finnish TimeZone converted datetime from given datetime. If naive datetime is given, it is assumed
        to be in utc timezone """
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = pytz.UTC.localize(dt)  # first make timezone aware
    return dt.astimezone(fitz)


def check_tz_info_attr(dt: datetime) -> None:
    if hasattr(dt, 'tzinfo') is False:
        raise AttributeError(f'Given object of type: {type(dt)} has no attribute "tzinfo"')


def fitzstr_from(dt: datetime) -> str:
    """ Finnish TimeZone converted string format. If :param: dt is None, returns empty string """
    fitz_dt = fitz_from(dt)
    if fitz_dt is None:
        return ''
    return fitz_dt.strftime(FINNISH_DATE_FORMAT)


def strptime_or_none(string: str, time_format: str) -> Optional[datetime]:
    """ tries to parse given string with given format and returns None if parsing fails for any reason"""
    try:
        return datetime.strptime(string, time_format)
    except (ValueError, TypeError):
        return None


def is_weekend(dt: datetime) -> bool:
    # Monday == 0 ... Saturday == 5, Sunday == 6
    return dt.weekday() >= 5


def next_weekday(dt: datetime) -> datetime:
    match dt.weekday():
        case 4:
            return dt + timedelta(days=3)
        case 5:
            return dt + timedelta(days=2)
        case _:
            return dt + timedelta(days=1)


def prev_weekday(dt: datetime) -> datetime:
    match dt.weekday():
        case 0:
            return dt - timedelta(days=3)
        case 6:
            return dt - timedelta(days=2)
        case _:
            return dt - timedelta(days=1)


def weekday_count_between(a: datetime, b: datetime) -> int:
    """ End date no included in the range. Order of dates does not matter """
    # Add utc timezone to make sure no naive and non-naive dt is compared
    a = utctz_from(a)
    b = utctz_from(b)
    # generate all days from d1 to d2
    # works almost perfect. For some reason gives some wrong results (for example 2004-01-01 to 2025-01-01 should be
    start: date = min(a, b).date()
    end: date = max(a, b).date()
    day_generator = (start + timedelta(x) for x in range((end - start).days))
    return sum(1 for day in day_generator if day.weekday() < 5)


def fi_short_day_name(dt: datetime) -> str:
    """ Week day index starts at 0 """
    return fi_short_day_name_from_day_index(dt.weekday())


def fi_short_day_name_from_day_index(week_day_index: int) -> str:
    """ Week day index starts at 0 """
    return fi_week_day_short_name_by_index[week_day_index]


fi_week_day_short_name_by_index = {0: 'ma', 1: 'ti', 2: 'ke', 3: 'to', 4: 'pe', 5: 'la', 6: 'su'}


def dt_at_midday(dt: datetime) -> datetime:
    return dt.replace(hour=12, minute=0, second=0, microsecond=0)


def excel_time(dt: datetime) -> float:
    """ Dates and times in Excel are represented by real numbers, for example “Jan 1 2013 12:00 PM”
    is represented by the number 41275.5. The integer part of the number stores the number of days
    since the epoch and the fractional part stores the percentage of the day. Excel does not support timezones """
    localized_dt = fitz_from(dt)
    return datetime_to_excel_datetime(localized_dt, False, True)


def excel_date(dt: datetime | date) -> str:
    localized_dt = fitz_from(dt)
    return datetime_to_excel_datetime(localized_dt, False, True)


def parse_dt_str_to_utctzstr(text: str) -> str | None:
    """ Parses date and returns it. If parameter is not valid date in any predefined format, None is returned """
    for date_format in ('%Y-%m-%d', '%d.%m.%Y', '%m/%d/%Y'):  # 2022-01-31, 31.01.2022, 01/31/2022
        try:
            # As only date is relevant, this is handled as Utc datetime with time of 00:00:00
            naive_dt = datetime.strptime(text, date_format)
            utc_transformed_dt = utctz_from(naive_dt)
            return str(utc_transformed_dt)
        except ValueError:
            pass
    return None

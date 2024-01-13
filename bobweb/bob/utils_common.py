import asyncio
import inspect
import logging
from datetime import datetime, timedelta, date
from decimal import Decimal
from functools import wraps
from typing import List, Sized, Tuple, Optional, Iterable

import pytz
from django.db.models import QuerySet
from telegram import Message, Update, Chat, ParseMode
from telegram.constants import ChatAction
from telegram.ext import CallbackContext
from xlsxwriter.utility import datetime_to_excel_datetime

from bobweb.bob.resources.bob_constants import FINNISH_DATE_FORMAT, fitz

logger = logging.getLogger(__name__)


async def auto_remove_msg_after_delay(msg: Message, context: CallbackContext, delay=5.0):
    async def implementation():
        await asyncio.sleep(delay)
        await remove_msg(msg, context)
    asyncio.get_running_loop().create_task(implementation())


async def remove_msg(msg: Message, context: CallbackContext) -> None:
    if context is not None:
        await context.bot.deleteMessage(chat_id=msg.chat_id, message_id=msg.message_id)


async def send_bot_is_typing_status_update(chat: Chat):
    """ Sends status update that adds 'Bot is typing...' text to the top of
        the active chat in users' clients. Should be only used, when there
        is a noticeable delay before next update. """
    await chat.send_chat_action(action=ChatAction.TYPING)


def reply_long_text(update: Update, text: str, quote: bool = False, parse_mode: ParseMode = None) -> Message:
    """
    Wrapper for Python Telegram Bot API's Message#reply_text that can handle
    long replies that contain messages with content length near or over Telegram's
    message content limit of 4096 characters. If text is over 4076 characters it is
    split into multiple messages that are decorated with number of current message
    and number of total messages. For example "[message content]... (1 / 2)"
    """
    telegram_message_max_length = 4096
    if len(text) > telegram_message_max_length:
        # text is split into chunks with smaller lenght to leave space for decorators
        chunks = split_to_chunks(text, 4070)
        chunk_count = len(chunks)
        for i, chunk in enumerate(chunks):
            end_decorator = f'... ({i + 1} / {chunk_count}'
            return update.effective_message.reply_text(chunk + end_decorator, quote=quote, parse_mode=parse_mode)
    else:
        return update.effective_message.reply_text(text, quote=quote, parse_mode=parse_mode)



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


def has_one(obj: object) -> bool:
    if obj is None:
        return False
    if isinstance(obj, QuerySet):
        return obj.count() == 1
    if hasattr(obj, "__len__"):
        return obj.__len__ == 1

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


def split_to_chunks(iterable: List | str, chunk_size: int):
    if iterable is None:
        return []
    if chunk_size <= 0:
        return iterable

    list_of_chunks = []
    for i in range(0, len(iterable), chunk_size):
        list_of_chunks.append(iterable[i:i + chunk_size])
    return list_of_chunks


def split_text(text: str, character_limit: int = 4000, chunks: List[str] = None) -> List[str]:
    """
    Splits text to word chunks limited by character count. Uses recursion to split given text.
    Uses fast inverse iteration that starts from the limit and iterates backwards to find first
    whitespace usage for ths split. As this is recursive, this fails if the text contains
    thousands of characters without space.
    :param text: that is split into "words"
    :param character_limit: number of characters each chunk can be long at most. Each chunks is split from
                            the last whitespace character before the limit so that words and other white space
                            delimited segments are kept intact. Any consecutive non-whitespace segment is broken
                            at the limit. (i.e. limit text: "text", limit: 3 => ['tex', 't']
    :param chunks: chunks from previous recursive call
    :return: List of strings ("chunks")
    """
    chunks = chunks or []
    if len(text) <= character_limit:
        # End recursion
        chunks.append(text)
        return chunks
    # Start from the end, iterate backwards until whitespace is next character
    i, c = character_limit, text[character_limit]
    while not c.isspace() and i > 1:
        i -= 1
        c = text[i]
    # Add chunk, do recursive call
    chunks.append(text[:i])
    skipped_chars = 1 if c.isspace() else 0
    return split_text(text[i + skipped_chars:], character_limit, chunks)


def flatten(item: any) -> List:
    if not item:  # Empty list or None
        return item
    if isinstance(item[0], list) or isinstance(item[0], tuple):
        return flatten(item[0]) + flatten(item[1:])
    return item[:1] + flatten(item[1:])


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

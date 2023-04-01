import inspect
import logging
import threading
from datetime import datetime, timedelta, date
from decimal import Decimal
from typing import List, Sized

import pytz
from django.db.models import QuerySet
from telegram import Message
from telegram.ext import CallbackContext

from bobweb.bob.resources.bob_constants import FINNISH_DATE_FORMAT, fitz

logger = logging.getLogger(__name__)


def auto_remove_msg_after_delay(msg: Message, context: CallbackContext, delay=5.0):
    threading.Timer(delay, lambda: remove_msg(msg, context)).start()


def remove_msg(msg: Message, context: CallbackContext) -> None:
    if context is not None:
        context.bot.deleteMessage(chat_id=msg.chat_id, message_id=msg.message_id)


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


def split_to_chunks(iterable: List, chunk_size: int):
    if iterable is None:
        return []
    if chunk_size <= 0:
        return iterable

    list_of_chunks = []
    for i in range(0, len(iterable), chunk_size):
        list_of_chunks.append(iterable[i:i + chunk_size])
    return list_of_chunks


def flatten(item: any) -> List:
    if not item:  # Empty list or None
        return item
    if isinstance(item[0], list):
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


def dict_search(data, *args, default: any = None):
    """
    Tries to get value from a nested dictionary using a list of keys/indices.
    Iterates through given keys / indices and for each string parameter assumes
    current node is a dict and tries to progress to a node with that name.
    For each index is assumed that current node is an array and tries to progress
    to a node in given index. If no error is raised by the traversal, returns
    last node.

    :param data: the dictionary to search. If not dict, error is raised out of
                 this function
    :param args: a list of keys/indices to traverse the dictionary. If none
                 or empty, given data is returned as is
    :param default: any value. Is returned instead of None if dict_search does
                    not find item from given path or exception is raised from
                    the search
    :return: the value in the nested dictionary or None if any exception occurs
    """
    traversed_path = ''

    if not isinstance(data, dict):
        raise TypeError(f'Expected first argument to be dict but got {type(data).__name__}')

    try:
        for arg in args:
            if isinstance(arg, str):
                if not isinstance(data, dict):
                    raise TypeError(f"Expected dict but got {type(data).__name__}")
                data = data[arg]
                traversed_path += f'[\'{arg}\']'
            elif isinstance(arg, int):
                if not isinstance(data, list) and not isinstance(data, tuple):
                    raise TypeError(f"Expected list or tuple but got "
                                    f"{type(data).__name__}")
                data = data[arg]
                traversed_path += f'[{arg}]'
            else:
                raise TypeError(f"Expected arguments to be of any type [str|int] "
                                f"but got {type(arg).__name__}")
        # Node in the last given specification
        return data
    except (KeyError, TypeError, IndexError) as e:
        # handle exceptions and return None
        if traversed_path == '':
            traversed_text = 'Error raised from dict root, no traversal done'
        else:
            traversed_text = f'Path traversed before error: {traversed_path}'

        caller: inspect.FrameInfo = get_caller_from_stack()
        logger.debug(f"Error searching value from dictionary: {e}. "
                     f"{traversed_text}. [module]: {inspect.getmodule(caller[0]).__name__}",
                     f" [function]: {caller.function}, [row]: {caller.lineno}, [*args content]: {str(args)}")

        return default  # given call parameter or default None


def get_caller_from_stack(stack_depth: int = 2, package_level_filter: int = 2) -> inspect.FrameInfo | None:
    """
    Note! The caller this function name is referencing is not caller of this fuction, but caller
    of the function that is calling this function!

    Returns FrameInfo of the function that was called in the stack before n (called_depth)
    calls before this function call. Filters the call stack to contain only calls given in
    current package and packages n levels (package_level_filter) above in the hierarchy

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
    :param package_level_filter: how many levels up from this functions package to look for
    :return: FrameInfo of the function in the given position of the filtered call stack
    """
    # get the current frame and the stack
    frame = inspect.currentframe()
    stack = inspect.getouterframes(frame)

    # Get context, meaning the function that called this one and is requesting its own caller
    context_frame = stack[1][0]
    context_package = inspect.getmodule(context_frame)
    context_package_list = context_package.__name__.rsplit('.')

    # Determine required package.
    # From the package of the context moved given filter amount of packages up in the hierarchy
    required_package = ''.join(context_package_list[0: len(context_package_list) - package_level_filter])

    current_depth = 0
    # iterate over the stack until we find a function that is in the package level scope and call depth
    for i in range(0, len(stack)):
        frame = stack[i][0]
        module = inspect.getmodule(frame)
        if module is None:
            continue
        if not module.__name__.startswith(required_package):
            continue
        if current_depth == stack_depth:
            return stack[i]
        else:
            current_depth += 1

    # if we reach the end of the stack without finding a caller, return None
    return None


def utctz_from(dt: datetime) -> datetime:
    """ UTC TimeZone converted datetime from given datetime. If naive datetime is given, it is assumed
        to be in utc timezone already """
    check_tz_info_attr(dt)
    if dt.tzinfo is None:
        return pytz.UTC.localize(dt)
    return dt.astimezone(pytz.UTC)


def fitz_from(dt: datetime) -> datetime:
    """ FInnish TimeZone converted datetime from given datetime. If naive datetime is given, it is assumed
        to be in utc timezone """
    check_tz_info_attr(dt)
    if dt.tzinfo is None:
        pytz.UTC.localize(dt)  # first make timezone aware
    return dt.astimezone(fitz)


def check_tz_info_attr(dt: datetime) -> None:
    if hasattr(dt, 'tzinfo') is False:
        raise AttributeError(f'Given object of type: {type(dt)} has no attribute "tzinfo"')


def fitzstr_from(dt: datetime) -> str:
    """ FInnish TimeZone converted string format """
    return fitz_from(dt).strftime(FINNISH_DATE_FORMAT)


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

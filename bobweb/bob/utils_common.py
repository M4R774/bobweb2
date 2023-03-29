import threading
from datetime import datetime, timedelta, date
from decimal import Decimal
from typing import List, Sized

import pytz
from django.db.models import QuerySet
from telegram import Message
from telegram.ext import CallbackContext

from bobweb.bob.resources.bob_constants import FINNISH_DATE_FORMAT, DEFAULT_TIMEZONE


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

    return True   # is not any above and is not None


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
    return dt.astimezone(DEFAULT_TIMEZONE)


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
        case 4: return dt + timedelta(days=3)
        case 5: return dt + timedelta(days=2)
        case _: return dt + timedelta(days=1)


def prev_weekday(dt: datetime) -> datetime:
    match dt.weekday():
        case 0: return dt - timedelta(days=3)
        case 6: return dt - timedelta(days=2)
        case _: return dt - timedelta(days=1)


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

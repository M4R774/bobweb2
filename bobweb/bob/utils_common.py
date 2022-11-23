import threading
from datetime import datetime, timedelta, date
from typing import List, Sized

import pytz
from django.db.models import QuerySet
from telegram import Message
from telegram.ext import CallbackContext

from bobweb.bob.resources.bob_constants import FINNISH_DATE_FORMAT, tzfi


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


def utctz_from(dt: datetime) -> datetime:
    """ UTC TimeZone converted datetime from given datetime """
    return dt.replace(tzinfo=pytz.UTC)


def fitz_from(dt: datetime) -> datetime:
    """ FInnish TimeZone converted datetime from given datetime """
    return dt.replace(tzinfo=tzfi)



def is_weekend(d: datetime) -> bool:
    # Monday == 0 ... Saturday == 5, Sunday == 6
    return d.weekday() >= 5


def next_weekday(d: datetime) -> datetime:
    match d.weekday():
        case 4: return d + timedelta(days=3)
        case 5: return d + timedelta(days=2)
        case _: return d + timedelta(days=1)


def prev_weekday(d: datetime) -> datetime:
    match d.weekday():
        case 0: return d - timedelta(days=3)
        case 6: return d - timedelta(days=2)
        case _: return d - timedelta(days=1)


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


def d_fi_name(d: datetime) -> str:
    match d.weekday():
        case 0: return 'ma'
        case 1: return 'ti'
        case 2: return 'ke'
        case 3: return 'to'
        case 4: return 'pe'
        case 5: return 'la'
        case 6: return 'su'


def start_of_date(d: datetime) -> datetime:
    return d.replace(hour=0, minute=0, second=0, microsecond=0)

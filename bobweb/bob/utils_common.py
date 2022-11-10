from datetime import datetime, timedelta
from typing import List, Iterable, Sized

from django.db.models import QuerySet


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


def is_weekend(target_datetime: datetime):
    # Monday == 1 ... Saturday == 6, Sunday == 7
    return target_datetime.isoweekday() >= 6


def get_next_weekday(target_datetime: datetime):
    if target_datetime.isoweekday() == 5:
        return target_datetime + timedelta(days=3)
    elif target_datetime.isoweekday() == 6:
        return target_datetime + timedelta(days=2)
    else:
        return target_datetime + timedelta(days=1)


def start_of_date(target_datetime: datetime) -> datetime:
    return target_datetime.replace(hour=0, minute=0, second=0, microsecond=0)

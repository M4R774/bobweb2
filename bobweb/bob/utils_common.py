from django.db.models import QuerySet


def has(obj) -> bool:
    if obj is None:
        return False

    if isinstance(obj, QuerySet):
        return obj.count() > 0
    if hasattr(obj, "__len__"):
        return obj.__len__ > 0

    # is not any above and is not None
    return True


def has_one(query_set: QuerySet) -> bool:
    return query_set.count() == 1


def has_no(query_set: QuerySet) -> bool:
    return query_set.count() == 0

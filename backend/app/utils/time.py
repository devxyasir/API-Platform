"""Time helpers — always timezone-aware UTC."""
from __future__ import annotations

from datetime import datetime, timezone


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def ensure_aware(dt: datetime | None) -> datetime | None:
    """Coerce a datetime to timezone-aware UTC.

    SQLite (the default local backend) does not preserve tzinfo, so datetimes
    read back from the database are naive. Comparing them against ``utcnow()``
    would raise ``TypeError: can't subtract offset-naive and offset-aware``.
    This normalizes any value before such comparisons.
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def to_epoch(dt: datetime | None) -> int:
    if dt is None:
        return 0
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp())


def isoformat(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def day_start(dt: datetime | None = None) -> datetime:
    """UTC midnight at the start of ``dt``'s day (default: today)."""
    dt = ensure_aware(dt) or utcnow()
    return dt.replace(hour=0, minute=0, second=0, microsecond=0)


def month_start(dt: datetime | None = None) -> datetime:
    """UTC start of ``dt``'s calendar month (default: this month)."""
    dt = ensure_aware(dt) or utcnow()
    return dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def hour_start(dt: datetime | None = None) -> datetime:
    """UTC start of ``dt``'s hour (default: this hour)."""
    dt = ensure_aware(dt) or utcnow()
    return dt.replace(minute=0, second=0, microsecond=0)


def add_months(dt: datetime, months: int) -> datetime:
    """Add ``months`` calendar months, clamping the day to the target month's length
    (e.g. Jan 31 + 1 month → Feb 28/29)."""
    dt = ensure_aware(dt) or utcnow()
    zero = dt.month - 1 + months
    year = dt.year + zero // 12
    month = zero % 12 + 1
    # Days in the target month (handles leap years via a march-1-minus-a-day trick).
    if month == 12:
        next_month_first = dt.replace(year=year + 1, month=1, day=1)
    else:
        next_month_first = dt.replace(year=year, month=month + 1, day=1)
    from datetime import timedelta

    last_day = (next_month_first - timedelta(days=1)).day
    return dt.replace(year=year, month=month, day=min(dt.day, last_day))

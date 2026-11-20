"""Time helpers shared by every module. Timestamps are stored in UTC; days are Indian days."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30), "IST")


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def aware(dt: datetime | None) -> datetime | None:
    """SQLite hands back naive datetimes for tz-aware columns; treat them as UTC."""
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def iso(dt: datetime | None) -> str | None:
    dt = aware(dt)
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z") if dt else None


def ist_day(now: datetime | None = None) -> date:
    return aware(now or now_utc()).astimezone(IST).date()


def ist_day_start(now: datetime | None = None) -> datetime:
    """Midnight IST of the current Indian day, in UTC."""
    d = ist_day(now)
    return datetime(d.year, d.month, d.day, tzinfo=IST).astimezone(timezone.utc)


def ist_week_start(now: datetime | None = None) -> datetime:
    """Monday 00:00 IST of the current week, in UTC."""
    start = ist_day_start(now)
    return start - timedelta(days=ist_day(now).weekday())

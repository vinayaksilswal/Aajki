"""Operations reporting (SOW 3.7): active users, funnel, retention, forecast volume, error
trends and sentiment-index health. Everything here is pseudonymous counts."""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.clock import ist_day, now_utc
from app.db import session_scope
from app.modules.engagement import service as engagement
from app.modules.forecasts import participation
from app.modules.governance.models import ErrorDay
from app.modules.identity import service as identity
from app.observability import log


def record_error(kind: str) -> None:
    """Count one server error for today's trend. Never raises: reporting must not add failures."""
    try:
        with session_scope() as s:
            insert = pg_insert if s.bind.dialect.name == "postgresql" else sqlite_insert
            s.execute(insert(ErrorDay).values(day=ist_day(), kind=kind, count=1)
                      .on_conflict_do_update(index_elements=[ErrorDay.day, ErrorDay.kind],
                                             set_={"count": ErrorDay.count + 1}))
    except Exception:  # pragma: no cover - the database itself may be what failed
        log.warning("could not record error count")


def error_trend(s: Session, days: int = 14) -> list[tuple[str, int]]:
    since = ist_day() - timedelta(days=days - 1)
    counts: dict[str, int] = {}
    for day, n in s.execute(select(ErrorDay.day, ErrorDay.count).where(ErrorDay.day >= since)).all():
        counts[day.isoformat()] = counts.get(day.isoformat(), 0) + n
    return [((since + timedelta(days=i)).isoformat(), counts.get((since + timedelta(days=i)).isoformat(), 0))
            for i in range(days)]


def funnel(s: Session, days: int = 30) -> dict:
    """Of the accounts created in the last `days` days: how many made a call, checked in,
    and came back on a later day."""
    users = identity.cohort(s, now_utc() - timedelta(days=days))
    ids = [u for u, _ in users]
    active = identity.active_days(s, ids)
    created = dict(users)
    returned = sum(1 for u in ids if any(d > ist_day(created[u]) for d in active.get(u, ())))
    return {"days": days, "new_accounts": len(ids),
            "made_a_call": len(participation.users_with_calls(s, ids)),
            "checked_in": len(engagement.users_checked_in(s, ids)), "came_back": returned}


def retention(s: Session, weeks: int = 6) -> list[dict]:
    """Weekly sign-up cohorts: share active again 1, 7 and 30 days after joining."""
    users = identity.cohort(s, now_utc() - timedelta(weeks=weeks))
    active = identity.active_days(s, [u for u, _ in users])
    today = ist_day()
    cohorts: dict[str, list] = {}
    for uid, created in users:
        d = ist_day(created)
        week = (d - timedelta(days=d.weekday())).isoformat()
        cohorts.setdefault(week, []).append((uid, d))
    out = []
    for week in sorted(cohorts, reverse=True):
        members = cohorts[week]
        row = {"week": week, "size": len(members)}
        for n in (1, 7, 30):
            eligible = [(u, d) for u, d in members if d + timedelta(days=n) <= today]
            back = sum(1 for u, d in eligible if any(x >= d + timedelta(days=n) for x in active.get(u, ())))
            row[f"d{n}"] = round(back / len(eligible), 3) if eligible else None
        out.append(row)
    return out

"""National sentiment dashboard (spec s.2, s.6; SOW 2.11).

Only aggregates leave this module: no user identifiers, and no figure for any group (a
question or a category) with fewer than MIN_GROUP participants. Election-sensitive questions
covered by a quiet period that hides sentiment are left out entirely. Results are cached per
instance for CACHE_SECONDS.
"""
from __future__ import annotations

import time
from collections import defaultdict
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.clock import aware, ist_day, ist_day_start, iso, now_utc
from app.modules.forecasts import service as forecasts
from app.modules.forecasts.models import CATEGORIES, Call, Question

MIN_GROUP = 50
CACHE_SECONDS = 60
TREND_DAYS = 7
_cache: dict = {}


def dashboard(s: Session, quiet: set[str]) -> dict:
    key = ",".join(sorted(quiet))
    hit = _cache.get(key)
    if hit and time.monotonic() - hit[0] < CACHE_SECONDS:
        return hit[1]
    data = _compute(s, quiet)
    _cache.clear()
    _cache[key] = (time.monotonic(), data)
    return data


def clear_cache() -> None:
    _cache.clear()


def _compute(s: Session, quiet: set[str]) -> dict:
    now = now_utc()
    window_start = now - timedelta(days=TREND_DAYS)
    qs = [q for q in s.scalars(select(Question).where(
        Question.status.in_(("published", "settled")), Question.opens_at <= now,
        Question.closes_at > window_start)).all()
        if not forecasts.chance_hidden(q, quiet)]
    ids = [q.id for q in qs]
    calls = s.execute(select(Call.question_id, Call.user_id, Call.outcome_key, Call.points, Call.created_at)
                      .where(Call.question_id.in_(ids))).all() if ids else []
    per_q: dict[str, list] = defaultdict(list)
    for row in calls:
        per_q[row[0]].append(row)

    def share_yes(rows, before=None) -> float | None:
        pts = defaultdict(int)
        for _, _, key, p, created in rows:
            if before is None or aware(created) < before:
                pts[key] += p
        total = sum(pts.values())
        return pts.get("yes", 0) / total if total else None

    questions, cats = [], defaultdict(lambda: {"questions": 0, "users": set(), "lean": 0.0, "weight": 0})
    for q in qs:
        rows = per_q.get(q.id, [])
        users = {r[1] for r in rows}
        c = cats[q.category]
        c["questions"] += 1
        c["users"] |= users
        if len(users) < MIN_GROUP:
            continue
        now_yes = share_yes(rows)
        day_ago = share_yes(rows, now - timedelta(days=1))
        trend = []
        for i in range(TREND_DAYS - 1, -1, -1):
            end = ist_day_start(now) - timedelta(days=i - 1)
            v = share_yes(rows, end)
            trend.append({"day": (ist_day(now) - timedelta(days=i)).isoformat(),
                          "chance_yes": round(v, 4) if v is not None else None})
        labels = {o["key"]: o["label"] for o in q.outcomes or []}
        lean = max(now_yes, 1 - now_yes)
        c["lean"] += lean * len(users)
        c["weight"] += len(users)
        questions.append({"id": q.id, "title": q.title, "category": q.category,
                          "yes_label": labels.get("yes", "Yes"), "participants": len(users),
                          "chance_yes": round(now_yes, 4),
                          "shift_24h": round(now_yes - day_ago, 4) if day_ago is not None else None,
                          "status": forecasts.effective_status(q, now), "trend": trend})

    categories = []
    for key, label in CATEGORIES.items():
        c = cats.get(key)
        if not c:
            continue
        enough = len(c["users"]) >= MIN_GROUP and c["weight"] > 0
        categories.append({"key": key, "label": label, "questions": c["questions"],
                           "participants": len(c["users"]) if enough else None,
                           "average_lean": round(c["lean"] / c["weight"], 4) if enough else None,
                           "enough_data": enough})
    movers = sorted((q for q in questions if q["shift_24h"] is not None),
                    key=lambda q: abs(q["shift_24h"]), reverse=True)[:5]
    decisive = sorted(questions, key=lambda q: abs(q["chance_yes"] - 0.5), reverse=True)[:5]
    contested = sorted(questions, key=lambda q: abs(q["chance_yes"] - 0.5))[:5]
    return {"as_of": iso(now), "min_group": MIN_GROUP, "categories": categories,
            "movers": movers, "decisive": decisive, "contested": contested,
            "questions_shown": len(questions), "questions_considered": len(qs),
            "election_restricted": bool(quiet)}


def health(s: Session, quiet: set[str]) -> dict:
    """Sentiment index health for operations: is it computing, and is it consistent?"""
    started = time.monotonic()
    data = _compute(s, quiet)
    took_ms = int((time.monotonic() - started) * 1000)
    bad = [q["id"] for q in data["movers"] + data["decisive"]
           if not 0 <= q["chance_yes"] <= 1]
    return {"computed_in_ms": took_ms, "questions_considered": data["questions_considered"],
            "questions_with_enough_data": data["questions_shown"],
            "categories_with_enough_data": sum(1 for c in data["categories"] if c["enough_data"]),
            "inconsistent": bad, "as_of": data["as_of"]}

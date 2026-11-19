"""Admin-only sentiment signal (question-wording tone + crowd lean), cached per instance.

The public, anonymised sentiment dashboard with a minimum group size of 50 is M5.
"""
from __future__ import annotations

import time

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.debate import service as debate
from app.modules.forecasts import service as forecasts
from app.modules.forecasts.models import Question
from app.modules.sentiment import lexicon

TTL_SECONDS = 60
_cache: dict = {"at": 0.0, "model": None}


def model(s: Session) -> dict:
    now = time.monotonic()
    if _cache["model"] is None or now - _cache["at"] > TTL_SECONDS:
        _cache["model"], _cache["at"] = lexicon.analyze_set(_inputs(s)), now
    return _cache["model"]


def _inputs(s: Session) -> list[dict]:
    qs = s.scalars(select(Question).where(Question.status != "draft")).all()
    ids = [q.id for q in qs]
    calls = forecasts.participation(s, ids)
    comments = debate.visible_counts(s, ids)
    out = []
    for q in qs:
        c = calls.get(q.id, {})
        options = [{"id": o["key"], "label": o["label"], "votes": c.get(o["key"], 0)}
                   for o in q.outcomes or []]
        out.append({"id": q.id, "question": q.title, "category": q.category, "options": options,
                    "total_votes": sum(o["votes"] for o in options),
                    "comment_count": comments.get(q.id, 0)})
    return out


def clear_cache() -> None:
    _cache["model"], _cache["at"] = None, 0.0

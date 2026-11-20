"""Question lifecycle, validation and public read model.

Lifecycle (stored -> what users see):
    draft                      -> not public
    published, before opens_at -> "scheduled" (not public yet)
    published, open window     -> "open"
    published, after closes_at -> "closed"
    paused / voided / settled  -> as stored
A question can be published only with a closing time, a resolution source and a rule
(spec s.3). Once published, the terms users forecast on are locked; to change them an
admin voids the question and drafts a new one.
"""
from __future__ import annotations

import base64
import json
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.clock import IST, aware, iso, now_utc  # noqa: F401  (re-exported for callers)
from app.errors import AppError, not_found
from app.ids import new_id
from app.modules.forecasts.models import CATEGORIES, Call, Question, Topic

MAX_PAGE = 50
MIN_LEAD = timedelta(minutes=5)          # a question must stay open at least this long
LOCKED_AFTER_PUBLISH = ("title", "category", "outcomes", "opens_at", "closes_at",
                        "resolution_source_url", "resolution_rule")
# Spec s.1/s.7 vocabulary rule: these never appear in product copy.
_FORBIDDEN = re.compile(r"\b(odds|bet|bets|betting|wager\w*|stake|stakes|staked|payouts?|"
                        r"portfolio|gambl\w*|jackpot)\b", re.IGNORECASE)


def effective_status(q: Question, now: datetime | None = None) -> str:
    if q.status != "published":
        return q.status
    now = now or now_utc()
    if q.opens_at and now < aware(q.opens_at):
        return "scheduled"
    if q.closes_at and now >= aware(q.closes_at):
        return "closed"
    return "open"


def is_public(q: Question, now: datetime | None = None) -> bool:
    return effective_status(q, now) not in ("draft", "scheduled")


# ----------------------------------------------------------------------------- validation

def _https(url: str | None) -> bool:
    if not url:
        return False
    p = urlparse(url)
    return p.scheme == "https" and bool(p.netloc)


def _vocab(field: str, text: str | None, problems: dict) -> None:
    m = _FORBIDDEN.search(text or "")
    if m:
        problems[field] = f'"{m.group(0)}" is not allowed. Use forecast, call, chance, points or reward.'


def draft_problems(d: dict) -> dict[str, str]:
    """Checks every draft must pass. `d` holds plain values (see admin form parsing)."""
    p: dict[str, str] = {}
    title = (d.get("title") or "").strip()
    if not 10 <= len(title) <= 200:
        p["title"] = "Write the question in 10 to 200 characters."
    _vocab("title", title, p)
    if d.get("category") not in CATEGORIES:
        p["category"] = "Choose one of the six categories."
    labels = [(o.get("label") or "").strip() for o in d.get("outcomes") or []]
    if len(labels) != 2 or not all(labels):
        p["outcomes"] = "Give both outcomes a label."
    elif labels[0].lower() == labels[1].lower():
        p["outcomes"] = "The two outcomes must differ."
    elif any(len(lbl) > 40 for lbl in labels):
        p["outcomes"] = "Keep each outcome label to 40 characters."
    else:
        for lbl in labels:
            _vocab("outcomes", lbl, p)
    _vocab("description", d.get("description"), p)
    if d.get("image_url") and not _https(d["image_url"]):
        p["image_url"] = "Use an https:// image link."
    if d.get("resolution_source_url") and not _https(d["resolution_source_url"]):
        p["resolution_source_url"] = "Use the official source's https:// link."
    opens, closes = d.get("opens_at"), d.get("closes_at")
    if opens and closes and closes <= opens:
        p["closes_at"] = "Closing time must be after opening time."
    return p


def publish_problems(q: Question, now: datetime | None = None) -> dict[str, str]:
    now = now or now_utc()
    d = _as_dict(q)
    p = draft_problems(d)
    if not q.closes_at:
        p.setdefault("closes_at", "Set a closing time.")
    elif aware(q.closes_at) < now + MIN_LEAD:
        p.setdefault("closes_at", "Closing time must be at least 5 minutes from now.")
    if not q.resolution_source_url:
        p.setdefault("resolution_source_url", "Add the official source used to settle this question.")
    if len((q.resolution_rule or "").strip()) < 20:
        p.setdefault("resolution_rule", "Explain in a sentence or two how the result will be decided.")
    return p


def _as_dict(q: Question) -> dict:
    return {"title": q.title, "category": q.category, "outcomes": q.outcomes,
            "description": q.description, "image_url": q.image_url,
            "resolution_source_url": q.resolution_source_url,
            "resolution_rule": q.resolution_rule,
            "opens_at": aware(q.opens_at), "closes_at": aware(q.closes_at)}


def binary_outcomes(yes_label: str, no_label: str) -> list[dict]:
    return [{"key": "yes", "label": (yes_label or "").strip()},
            {"key": "no", "label": (no_label or "").strip()}]


def _slug(title: str, fallback: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:80] or fallback


# ----------------------------------------------------------------------------- admin writes

def _utc_fields(d: dict) -> dict:
    """Store every timestamp in UTC (SQLite drops offsets; one rule for all backends)."""
    return {k: (aware(v).astimezone(timezone.utc) if isinstance(v, datetime) else v)
            for k, v in d.items()}


def create_draft(s: Session, d: dict) -> Question:
    d = _utc_fields(d)
    problems = draft_problems(d)
    if problems:
        raise AppError(422, "VALIDATION_FAILED", "Fix the highlighted fields.", problems)
    qid = new_id("q")
    q = Question(id=qid, slug=_slug(d["title"], qid), status="draft",
                 **{k: d.get(k) for k in _EDITABLE})
    s.add(q)
    s.flush()
    return q


_EDITABLE = ("title", "category", "outcomes", "description", "image_url", "topic_id",
             "opens_at", "closes_at", "resolution_source_url", "resolution_rule",
             "election_sensitive", "election_state", "trending", "source_headline", "source_link")


def update(s: Session, q: Question, d: dict) -> Question:
    d = _utc_fields(d)
    if q.status in ("voided", "settled"):
        raise AppError(409, "CONFLICT", "Voided or settled questions can't be edited.")
    if q.status != "draft":
        changed = [f for f in LOCKED_AFTER_PUBLISH if f in d and _differs(getattr(q, f), d[f])]
        if changed:
            raise AppError(409, "LOCKED", "These terms are locked once published. Void the "
                           "question and draft a new one to change them.", {f: "locked" for f in changed})
    merged = {**_as_dict(q), **{k: v for k, v in d.items() if k in _EDITABLE}}
    problems = draft_problems(merged)
    if problems:
        raise AppError(422, "VALIDATION_FAILED", "Fix the highlighted fields.", problems)
    for k, v in d.items():
        if k in _EDITABLE:
            setattr(q, k, v)
    if q.status == "draft":
        q.slug = _slug(q.title, q.id)
    return q


def _differs(old, new) -> bool:
    if isinstance(old, datetime) or isinstance(new, datetime):
        return aware(old) != aware(new)
    return (old or None) != (new or None)


# action -> (allowed effective statuses, resulting stored status)
_TRANSITIONS = {
    "publish": (("draft",), "published"),
    "unpublish": (("scheduled",), "draft"),
    "pause": (("open",), "paused"),
    "resume": (("paused",), "published"),
    "void": (("scheduled", "open", "paused", "closed"), "voided"),
}


def transition(s: Session, q: Question, action: str, now: datetime | None = None) -> Question:
    now = now or now_utc()
    if action not in _TRANSITIONS:
        raise AppError(400, "BAD_REQUEST", f"Unknown action {action!r}.")
    allowed, target = _TRANSITIONS[action]
    current = effective_status(q, now)
    if current not in allowed:
        raise AppError(409, "CONFLICT", f"Can't {action} a question that is {current}.")
    if action == "publish":
        problems = publish_problems(q, now)
        if problems:
            raise AppError(422, "VALIDATION_FAILED", "Complete these before publishing.", problems)
        if not q.opens_at:
            q.opens_at = now
    if action == "resume" and q.closes_at and now >= aware(q.closes_at):
        raise AppError(409, "CONFLICT", "This question has passed its closing time.")
    q.status = target
    if action == "void":
        # A void returns every committed point automatically (spec s.3).
        from app.modules.forecasts import participation
        participation.refund_all(s, q, "Question cancelled: points returned")
    return q


def delete_draft(s: Session, q: Question) -> None:
    if q.status != "draft":
        raise AppError(409, "CONFLICT", "Only drafts can be deleted. Void a published question "
                       "instead, so its record is kept.")
    s.delete(q)


# ----------------------------------------------------------------------------- reads

def participation(s: Session, ids: list[str], before: datetime | None = None
                  ) -> dict[str, dict[str, dict[str, int]]]:
    """Per question and outcome: calls and points committed (one grouped query).
    `before` gives the picture as it stood at an earlier moment (consensus trends)."""
    out: dict[str, dict[str, dict[str, int]]] = defaultdict(dict)
    if ids:
        stmt = (select(Call.question_id, Call.outcome_key, func.count(), func.sum(Call.points))
                .where(Call.question_id.in_(ids)).group_by(Call.question_id, Call.outcome_key))
        if before is not None:
            stmt = stmt.where(Call.created_at < before)
        for qid, key, n, pts in s.execute(stmt).all():
            out[qid][key] = {"calls": int(n), "points": int(pts or 0)}
    return out


def chance(counts: dict[str, dict[str, int]], key: str) -> float | None:
    """Spec s.2: the consensus chance is each outcome's share of the points committed."""
    total = sum(v["points"] for v in counts.values())
    return round(counts.get(key, {}).get("points", 0) / total, 4) if total else None


def calls_by_user(s: Session) -> dict[str, int]:
    return dict(s.execute(select(Call.user_id, func.count()).group_by(Call.user_id)).all())


def counts(s: Session, now: datetime | None = None) -> dict[str, int]:
    now = now or now_utc()
    total = s.scalar(select(func.count()).select_from(Question)) or 0
    drafts = s.scalar(select(func.count()).select_from(Question)
                      .where(Question.status == "draft")) or 0
    open_ = s.scalar(select(func.count()).select_from(Question).where(
        Question.status == "published", Question.opens_at <= now, Question.closes_at > now)) or 0
    calls = s.scalar(select(func.count()).select_from(Call)) or 0
    awaiting = s.scalar(select(func.count()).select_from(Question).where(
        Question.status.in_(("published", "paused")), Question.closes_at <= now)) or 0
    return {"questions": total, "open": open_, "drafts": drafts, "calls": calls,
            "awaiting_result": awaiting}


def chance_hidden(q: Question, quiet: set[str]) -> bool:
    """Election-sensitive questions hide their live chance while a quiet period covers their
    state. "*" means every state; a question with no state is hidden by any quiet period."""
    if not q.election_sensitive or not quiet:
        return False
    return "*" in quiet or not q.election_state or q.election_state in quiet


def to_public(q: Question, counts: dict[str, dict[str, int]], quiet: set[str],
              now: datetime | None = None) -> dict:
    hidden = chance_hidden(q, quiet)
    total_calls = sum(v["calls"] for v in counts.values())
    outcomes = [{"key": o["key"], "label": o["label"],
                 "chance": None if hidden else chance(counts, o["key"])}
                for o in q.outcomes or []]
    return {
        "id": q.id, "category": q.category, "title": q.title,
        "description": q.description, "image_url": q.image_url,
        "status": effective_status(q, now),
        "opens_at": iso(q.opens_at), "closes_at": iso(q.closes_at),
        "outcomes": outcomes, "participants": total_calls, "chance_hidden": hidden,
        "resolution": {"source_url": q.resolution_source_url, "rule": q.resolution_rule},
        "election_sensitive": bool(q.election_sensitive), "election_state": q.election_state,
        "trending": bool(q.trending),
        "context": ({"headline": q.source_headline, "link": q.source_link}
                    if q.source_headline else None),
    }


def _decode_cursor(cursor: str | None) -> int:
    if not cursor:
        return 0
    try:
        offset = json.loads(base64.urlsafe_b64decode(cursor.encode()))["o"]
        if isinstance(offset, int) and 0 <= offset <= 10_000:
            return offset
    except Exception:
        pass
    raise AppError(400, "BAD_CURSOR", "That page link has expired. Reload the list.")


def _encode_cursor(offset: int) -> str:
    return base64.urlsafe_b64encode(json.dumps({"o": offset}).encode()).decode()


def list_public(s: Session, *, status: str = "open", category: str | None = None,
                search: str | None = None, sort: str = "closing", cursor: str | None = None,
                limit: int = 20, quiet: set[str] | None = None, now: datetime | None = None) -> dict:
    now = now or now_utc()
    if category and category not in CATEGORIES:
        raise AppError(400, "BAD_REQUEST", "Unknown category.")
    stmt = select(Question)
    if status == "open":
        stmt = stmt.where(Question.status == "published", Question.opens_at <= now,
                          Question.closes_at > now)
    elif status == "closed":
        stmt = stmt.where(Question.status == "published", Question.closes_at <= now)
    elif status == "settled":
        stmt = stmt.where(Question.status.in_(("settled", "voided")))
    else:
        raise AppError(400, "BAD_REQUEST", "status must be open, closed or settled.")
    if category:
        stmt = stmt.where(Question.category == category)
    if search:
        term = search.strip()[:80].replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        stmt = stmt.where(Question.title.ilike(f"%{term}%", escape="\\"))
    if sort == "trending":
        calls = (select(Call.question_id.label("qid"), func.count().label("n"))
                 .group_by(Call.question_id).subquery())
        stmt = (stmt.outerjoin(calls, calls.c.qid == Question.id)
                .order_by(func.coalesce(calls.c.n, 0).desc(), Question.trending.desc(),
                          Question.closes_at.asc(), Question.id))
    elif sort == "closing":
        # Open: closing soonest first. Closed or settled: most recent first.
        stmt = stmt.order_by(Question.closes_at.asc() if status == "open" else Question.closes_at.desc(),
                             Question.id)
    else:
        raise AppError(400, "BAD_REQUEST", "sort must be closing or trending.")
    limit = max(1, min(limit, MAX_PAGE))
    offset = _decode_cursor(cursor)
    rows = s.scalars(stmt.offset(offset).limit(limit + 1)).all()
    page, more = rows[:limit], len(rows) > limit
    counts = participation(s, [q.id for q in page])
    return {"items": [to_public(q, counts.get(q.id, {}), quiet or set(), now) for q in page],
            "next_cursor": _encode_cursor(offset + limit) if more else None,
            "as_of": iso(now)}


def get_public(s: Session, qid: str, quiet: set[str] | None = None,
               now: datetime | None = None) -> dict:
    q = s.get(Question, qid)
    if not q or not is_public(q, now):
        raise not_found("Question")
    return to_public(q, participation(s, [q.id]).get(q.id, {}), quiet or set(), now)


def open_question_ids(s: Session, ids: list[str], now: datetime | None = None) -> set[str]:
    """Which of these questions are currently open to calls (used to link ticker items)."""
    if not ids:
        return set()
    now = now or now_utc()
    return set(s.scalars(select(Question.id).where(
        Question.id.in_(ids), Question.status == "published",
        Question.opens_at <= now, Question.closes_at > now)).all())


# ----------------------------------------------------------------------------- admin reads

def admin_rows(s: Session) -> list[dict]:
    qs = s.scalars(select(Question).order_by(Question.created_at.desc())).all()
    counts = participation(s, [q.id for q in qs])
    now = now_utc()
    return [{"id": q.id, "title": q.title, "category": q.category,
             "status": effective_status(q, now), "closes_at": aware(q.closes_at),
             "participants": sum(v["calls"] for v in counts.get(q.id, {}).values()),
             "election_sensitive": q.election_sensitive} for q in qs]


def topics(s: Session) -> list[Topic]:
    return list(s.scalars(select(Topic).order_by(Topic.title)).all())


def get(s: Session, qid: str) -> Question:
    q = s.get(Question, qid)
    if not q:
        raise not_found("Question")
    return q

"""Election quiet periods and grievances."""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.clock import aware, iso, now_utc
from app.config import get_settings
from app.errors import AppError, not_found
from app.ids import new_id
from app.modules.compliance.models import Grievance, GrievanceNote, QuietPeriod
from app.regions import STATES

ACK_TARGET = timedelta(hours=24)
RESOLVE_TARGET = timedelta(days=15)
GRIEVANCE_CATEGORIES = {
    "result": "A question's result", "points": "My points", "content": "A comment or post",
    "account": "My account or a suspension", "privacy": "My personal data", "other": "Something else",
}


# ----------------------------------------------------------------------------- quiet periods

def quiet_states(s: Session, now: datetime | None = None, sentiment: bool = False) -> set[str]:
    """States under an active quiet period ("*" = all). ELECTION_QUIET_PERIOD=true in the
    environment is an emergency switch that covers every state."""
    now = now or now_utc()
    out: set[str] = {"*"} if get_settings().election_quiet_period else set()
    stmt = select(QuietPeriod.states).where(QuietPeriod.starts_at <= now, QuietPeriod.ends_at > now)
    if sentiment:
        stmt = stmt.where(QuietPeriod.hide_sentiment.is_(True))
    for states in s.scalars(stmt).all():
        out.update(x.strip() for x in states.split(",") if x.strip())
    return out


def periods(s: Session) -> list[QuietPeriod]:
    return list(s.scalars(select(QuietPeriod).order_by(QuietPeriod.starts_at.desc()).limit(100)).all())


def add_period(s: Session, label: str, states: list[str], starts_at: datetime, ends_at: datetime,
               hide_sentiment: bool, admin_id: str) -> QuietPeriod:
    label = (label or "").strip()
    if not 3 <= len(label) <= 120:
        raise AppError(422, "VALIDATION_FAILED", "Name the period (3 to 120 characters).")
    if not states:
        raise AppError(422, "VALIDATION_FAILED", "Choose at least one state, or all states.")
    if states != ["*"] and any(x not in STATES for x in states):
        raise AppError(422, "VALIDATION_FAILED", "Unknown state code.")
    if not starts_at or not ends_at or ends_at <= starts_at:
        raise AppError(422, "VALIDATION_FAILED", "The period must end after it starts.")
    p = QuietPeriod(id=new_id("qp"), label=label, states=",".join(states), starts_at=starts_at,
                    ends_at=ends_at, hide_sentiment=hide_sentiment, created_by=admin_id)
    s.add(p)
    s.flush()
    return p


def end_period(s: Session, pid: str) -> QuietPeriod:
    p = s.get(QuietPeriod, pid)
    if not p:
        raise not_found("Quiet period")
    now = now_utc()
    if aware(p.ends_at) > now:
        p.ends_at = max(now, aware(p.starts_at))
    return p


def period_snapshot(p: QuietPeriod) -> dict:
    return {"label": p.label, "states": p.states, "starts_at": iso(p.starts_at),
            "ends_at": iso(p.ends_at), "hide_sentiment": p.hide_sentiment}


# ----------------------------------------------------------------------------- grievances

def _out(g: Grievance, notes: list[GrievanceNote]) -> dict:
    return {"id": g.id, "ref": g.ref, "category": g.category, "subject": g.subject,
            "description": g.description, "status": g.status, "question_id": g.question_id,
            "support_review_consent": g.support_review_consent,
            "created_at": iso(g.created_at), "acknowledged_at": iso(g.acknowledged_at),
            "resolved_at": iso(g.resolved_at), "resolution": g.resolution,
            "updates": [{"note": n.note, "at": iso(n.created_at)} for n in notes if n.visible_to_user]}


def raise_grievance(s: Session, user_id: str, category: str, subject: str, description: str,
                    question_id: str | None, consent: bool) -> dict:
    if category not in GRIEVANCE_CATEGORIES:
        raise AppError(422, "VALIDATION_FAILED", "Choose what your complaint is about.")
    subject, description = (subject or "").strip(), (description or "").strip()
    if not 5 <= len(subject) <= 140:
        raise AppError(422, "VALIDATION_FAILED", "Give a short subject (5 to 140 characters).")
    if not 20 <= len(description) <= 3000:
        raise AppError(422, "VALIDATION_FAILED", "Describe the problem in 20 to 3,000 characters.")
    g = Grievance(id=new_id("grv"), ref="BF-" + "".join(secrets.choice("ABCDEFGHJKMNPQRSTUVWXYZ23456789")
                                                       for _ in range(7)),
                  user_id=user_id, category=category, subject=subject, description=description,
                  question_id=(question_id or None), support_review_consent=bool(consent))
    s.add(g)
    s.flush()
    return _out(g, [])


def _notes(s: Session, ids: list[str]) -> dict[str, list[GrievanceNote]]:
    out: dict[str, list[GrievanceNote]] = {i: [] for i in ids}
    if ids:
        for n in s.scalars(select(GrievanceNote).where(GrievanceNote.grievance_id.in_(ids))
                           .order_by(GrievanceNote.created_at)).all():
            out[n.grievance_id].append(n)
    return out


def my_grievances(s: Session, user_id: str) -> list[dict]:
    gs = s.scalars(select(Grievance).where(Grievance.user_id == user_id)
                   .order_by(Grievance.created_at.desc())).all()
    notes = _notes(s, [g.id for g in gs])
    return [_out(g, notes[g.id]) for g in gs]


def get(s: Session, gid: str) -> Grievance:
    g = s.get(Grievance, gid)
    if not g:
        raise not_found("Grievance")
    return g


def admin_queue(s: Session, status: str | None) -> list[dict]:
    stmt = select(Grievance).order_by(Grievance.created_at)
    if status == "active":
        stmt = stmt.where(Grievance.status.in_(("open", "in_progress")))
    elif status:
        stmt = stmt.where(Grievance.status == status)
    now = now_utc()
    rows = []
    for g in s.scalars(stmt.limit(300)).all():
        created = aware(g.created_at)
        rows.append({"g": g, "ack_overdue": not g.acknowledged_at and now - created > ACK_TARGET,
                     "resolve_overdue": g.status in ("open", "in_progress") and now - created > RESOLVE_TARGET,
                     "age_hours": int((now - created).total_seconds() // 3600)})
    return rows


def notes_for(s: Session, gid: str) -> list[GrievanceNote]:
    return _notes(s, [gid])[gid]


def snapshot(g: Grievance) -> dict:
    return {"status": g.status, "assigned_to": g.assigned_to, "resolution": g.resolution}


def update(s: Session, g: Grievance, admin_id: str, status: str, note: str, visible: bool,
           resolution: str | None) -> Grievance:
    if status not in ("open", "in_progress", "resolved", "rejected"):
        raise AppError(422, "VALIDATION_FAILED", "Unknown status.")
    if g.status in ("resolved", "rejected") and status in ("resolved", "rejected"):
        raise AppError(409, "CONFLICT", "This complaint is already closed.")
    now = now_utc()
    if status in ("resolved", "rejected"):
        if len((resolution or "").strip()) < 10:
            raise AppError(422, "VALIDATION_FAILED", "Write the outcome the user will see.")
        g.resolution, g.resolved_at = resolution.strip(), now
    if not g.acknowledged_at:
        g.acknowledged_at = now
    g.status, g.assigned_to = status, g.assigned_to or admin_id
    if (note or "").strip():
        s.add(GrievanceNote(grievance_id=g.id, admin_id=admin_id, note=note.strip()[:2000],
                            visible_to_user=visible))
    return g


def counts(s: Session) -> dict[str, int]:
    open_ = s.scalar(select(func.count()).select_from(Grievance).where(
        Grievance.status.in_(("open", "in_progress")))) or 0
    unacked = s.scalar(select(func.count()).select_from(Grievance).where(
        Grievance.acknowledged_at.is_(None), Grievance.created_at < now_utc() - ACK_TARGET)) or 0
    return {"grievances_open": open_, "grievances_unacknowledged": unacked}


def has_review_consent(s: Session, user_id: str, grievance_id: str) -> bool:
    g = s.get(Grievance, grievance_id)
    return bool(g and g.user_id == user_id and g.support_review_consent
                and g.status in ("open", "in_progress"))

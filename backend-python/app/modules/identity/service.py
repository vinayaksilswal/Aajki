"""Audience administration. Sign-in, sessions, consent and DPDP rights arrive in M2."""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.errors import not_found
from app.modules.identity.models import User


def mask_phone(phone: str | None) -> str:
    """Admins see enough to recognise a number, not the whole number (data minimisation)."""
    digits = (phone or "").strip()
    return digits[:3] + "•" * max(0, len(digits) - 5) + digits[-2:] if len(digits) > 5 else "•••"


def admin_list(s: Session, participation: dict[str, int]) -> list[dict]:
    users = s.scalars(select(User).order_by(User.created_at.desc()).limit(500)).all()
    return [{"id": u.id, "display_name": u.display_name, "handle": u.handle,
             "phone": mask_phone(u.phone), "blocked": u.blocked,
             "calls": participation.get(u.id, 0), "created_at": u.created_at} for u in users]


def counts(s: Session) -> dict[str, int]:
    total, blocked = s.execute(select(func.count(), func.count().filter(User.blocked.is_(True)))
                               .select_from(User)).one()
    return {"users": total, "blocked": blocked}


def set_blocked(s: Session, user_id: str, blocked: bool) -> None:
    u = s.get(User, user_id)
    if not u:
        raise not_found("User")
    u.blocked = blocked

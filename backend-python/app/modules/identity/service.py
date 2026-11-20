"""Accounts, app sessions, safeguards and audience administration.

Phone OTP, Google/Apple sign-in, the 18+ gate and consent records are M2 (deferred). Until
then each app install gets a pseudonymous device account.
"""
from __future__ import annotations

import hashlib
import re
import secrets
from datetime import datetime, timedelta  # noqa: F401

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.clock import aware, ist_day, ist_day_start, iso, now_utc
from app.config import get_settings
from app.errors import AppError, not_found
from app.ids import new_id
from app.modules.identity.models import ActivityDay, AppSession, User
from app.modules.ledger import service as ledger

SESSION_DAYS = 365
SELF_EXCLUSION_DAYS = (1, 7, 30, 90)
_NAME = re.compile(r"^[\w .\-]{3,24}$", re.UNICODE)
_RESERVED = re.compile(r"admin|moderator|official|foreseez|support|grievance", re.IGNORECASE)


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def mask_phone(phone: str | None) -> str:
    """Admins see enough to recognise a number, not the whole number (data minimisation)."""
    digits = (phone or "").strip()
    return digits[:3] + "•" * max(0, len(digits) - 5) + digits[-2:] if len(digits) > 5 else "—"


# ----------------------------------------------------------------------------- sessions

AVATARS = ("lotus", "tiger", "peacock", "elephant", "mango", "kite", "diya", "cricket")
_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def _invite_code() -> str:
    return "".join(secrets.choice(_CODE_ALPHABET) for _ in range(8))


def start_device_session(s: Session, invite_code: str | None = None) -> tuple[User, str]:
    """A new pseudonymous account with its welcome reward, and a bearer token for it."""
    uid = new_id("usr")
    inviter = None
    if invite_code:
        inviter = s.scalar(select(User.id).where(User.invite_code == invite_code.strip().upper()[:16]))
    user = User(id=uid, kind="device", display_name=f"Forecaster {uid[-4:]}",
                invite_code=_invite_code(), invited_by=inviter)
    s.add(user)
    s.flush()
    reward = get_settings().signup_reward
    # The welcome reward is a grant, not earned through play, so it doesn't count toward rank.
    ledger.post(s, "signup_reward", [(ledger.ISSUANCE, -reward), (ledger.available(uid), reward)],
                user_id=uid, memo="Welcome reward")
    token = secrets.token_urlsafe(32)
    now = now_utc()
    s.add(AppSession(id=new_id("ses"), user_id=uid, token_hash=_hash(token), created_at=now,
                     expires_at=now + timedelta(days=SESSION_DAYS)))
    return user, token


def authenticate(s: Session, token: str) -> User | None:
    if not token or len(token) > 200:
        return None
    now = now_utc()
    row = s.execute(select(AppSession, User).join(User, User.id == AppSession.user_id)
                    .where(AppSession.token_hash == _hash(token))).first()
    if not row:
        return None
    sess, user = row
    if sess.revoked_at or aware(sess.expires_at) <= now or user.blocked:
        return None
    return user


def record_activity(s: Session, user: User) -> None:
    """Mark today as active (pseudonymous DAU/MAU). At most one write per user per day."""
    now = now_utc()
    if user.last_seen_at and ist_day(aware(user.last_seen_at)) == ist_day(now):
        return
    insert = pg_insert if s.bind.dialect.name == "postgresql" else sqlite_insert
    s.execute(insert(ActivityDay).values(user_id=user.id, day=ist_day(now))
              .on_conflict_do_nothing(index_elements=[ActivityDay.user_id, ActivityDay.day]))
    s.query(User).filter(User.id == user.id).update({User.last_seen_at: now})


def revoke_sessions(s: Session, user_id: str) -> None:
    now = now_utc()
    for sess in s.scalars(select(AppSession).where(AppSession.user_id == user_id,
                                                   AppSession.revoked_at.is_(None))).all():
        sess.revoked_at = now


# ----------------------------------------------------------------------------- safeguards

def restriction(user: User, now: datetime | None = None) -> dict | None:
    """Why this user can't make calls or post right now, if they can't."""
    now = now or now_utc()
    if user.blocked:
        return {"code": "ACCOUNT_BLOCKED", "message": "This account has been blocked.", "until": None}
    if user.excluded_until and aware(user.excluded_until) > now:
        return {"code": "SELF_EXCLUDED", "until": iso(user.excluded_until),
                "message": "You chose to take a break. Calls and posts reopen when it ends."}
    if user.suspended_until and aware(user.suspended_until) > now:
        return {"code": "SUSPENDED", "until": iso(user.suspended_until),
                "message": "Your account is suspended for breaking the community rules."}
    return None


def ensure_can_participate(user: User) -> None:
    r = restriction(user)
    if r:
        raise AppError(403, r["code"], r["message"], {"until": r["until"]})


def self_exclude(s: Session, user_id: str, days: int) -> User:
    if days not in SELF_EXCLUSION_DAYS:
        raise AppError(422, "VALIDATION_FAILED", "Choose 1, 7, 30 or 90 days.")
    user = s.get(User, user_id)
    until = now_utc() + timedelta(days=days)
    # A break can be extended but never cut short.
    if not user.excluded_until or aware(user.excluded_until) < until:
        user.excluded_until = until
    return user


def set_display_name(s: Session, user_id: str, name: str) -> User:
    name = " ".join((name or "").split())
    if not _NAME.match(name):
        raise AppError(422, "VALIDATION_FAILED", "Use 3 to 24 letters, numbers, spaces, dots, "
                       "dashes or underscores.", {"display_name": "invalid"})
    if _RESERVED.search(name):
        raise AppError(422, "VALIDATION_FAILED", "That name could be mistaken for an official "
                       "account. Choose another.", {"display_name": "reserved"})
    user = s.get(User, user_id)
    user.display_name = name
    return user


def set_profile(s: Session, user_id: str, *, region: str | None = None, avatar: str | None = None,
                clear_region: bool = False) -> User:
    from app.regions import STATES
    user = s.get(User, user_id)
    if clear_region:
        user.region = None
    elif region is not None:
        if region not in STATES:
            raise AppError(422, "VALIDATION_FAILED", "Choose a state from the list.", {"region": "invalid"})
        user.region = region
    if avatar is not None:
        if avatar not in AVATARS:
            raise AppError(422, "VALIDATION_FAILED", "Choose one of the avatars.", {"avatar": "invalid"})
        user.avatar = avatar
    return user


def invites(s: Session, user_id: str) -> dict:
    """Invite tracking. Invites earn no points while accounts are unverified device accounts:
    a reward would be farmed by reinstalling the app (SOW 4.1.5). Rewards can start with
    phone sign-in."""
    joined = s.scalar(select(func.count()).select_from(User).where(User.invited_by == user_id)) or 0
    code = s.scalar(select(User.invite_code).where(User.id == user_id))
    return {"code": code, "joined": int(joined), "reward_per_invite": 0}


def delete_account(s: Session, user_id: str) -> None:
    """DPDP right to erasure. Personal details are removed and the account can no longer sign
    in. Ledger and call records stay as pseudonymous entries, so points totals, settled
    results and the audit trail remain correct."""
    user = s.get(User, user_id)
    user.kind, user.display_name, user.phone = "deleted", "Deleted user", None
    user.handle = user.region = user.avatar = user.invite_code = None
    user.blocked = True
    revoke_sessions(s, user_id)


def export(user: User) -> dict:
    return {"id": user.id, "display_name": user.display_name, "kind": user.kind,
            "region": user.region, "avatar": user.avatar, "invite_code": user.invite_code,
            "invited": bool(user.invited_by), "created_at": iso(user.created_at),
            "last_seen_at": iso(user.last_seen_at), "warnings": user.warnings,
            "suspended_until": iso(user.suspended_until), "excluded_until": iso(user.excluded_until)}


def names(s: Session, ids: list[str]) -> dict[str, str]:
    if not ids:
        return {}
    return dict(s.execute(select(User.id, User.display_name).where(User.id.in_(ids))).all())


def profiles(s: Session, ids: list[str]) -> dict[str, dict]:
    """Public profile fields only: the generated or chosen name and a preset avatar."""
    if not ids:
        return {}
    return {uid: {"display_name": name, "avatar": avatar} for uid, name, avatar in s.execute(
        select(User.id, User.display_name, User.avatar).where(User.id.in_(ids))).all()}


def blocked_ids(s: Session) -> set[str]:
    return set(s.scalars(select(User.id).where(User.blocked.is_(True))).all())


# ----------------------------------------------------------------------------- admin

def admin_list(s: Session, participation: dict[str, int], search: str | None = None) -> list[dict]:
    stmt = select(User).order_by(User.created_at.desc()).limit(500)
    if search:
        term = search.strip()[:40].replace("%", "").replace("_", "")
        stmt = stmt.where((User.display_name.ilike(f"%{term}%")) | (User.id == term))
    now = now_utc()
    return [{"id": u.id, "display_name": u.display_name, "kind": u.kind,
             "phone": mask_phone(u.phone), "blocked": u.blocked, "warnings": u.warnings,
             "restriction": restriction(u, now), "calls": participation.get(u.id, 0),
             "created_at": u.created_at, "last_seen_at": u.last_seen_at}
            for u in s.scalars(stmt).all()]


def get(s: Session, user_id: str) -> User:
    u = s.get(User, user_id)
    if not u:
        raise not_found("User")
    return u


def counts(s: Session) -> dict[str, int]:
    total, blocked = s.execute(select(func.count(), func.count().filter(User.blocked.is_(True)))
                               .select_from(User)).one()
    return {"users": total, "blocked": blocked}


def snapshot(u: User) -> dict:
    return {"blocked": u.blocked, "warnings": u.warnings, "suspended_until": iso(u.suspended_until)}


def set_blocked(s: Session, user_id: str, blocked: bool) -> User:
    u = get(s, user_id)
    u.blocked = blocked
    if blocked:
        revoke_sessions(s, user_id)
    return u


def warn(s: Session, user_id: str) -> User:
    u = get(s, user_id)
    u.warnings = (u.warnings or 0) + 1
    return u


def suspend(s: Session, user_id: str, days: int) -> User:
    if days not in (1, 3, 7, 30):
        raise AppError(422, "VALIDATION_FAILED", "Suspend for 1, 3, 7 or 30 days.")
    u = get(s, user_id)
    u.suspended_until = now_utc() + timedelta(days=days)
    return u


def unsuspend(s: Session, user_id: str) -> User:
    u = get(s, user_id)
    u.suspended_until = None
    return u


def activity(s: Session) -> dict[str, int]:
    """Pseudonymous active-user counts for the operations dashboard."""
    today = ist_day()
    dau = s.scalar(select(func.count()).select_from(ActivityDay).where(ActivityDay.day == today)) or 0
    wau = s.scalar(select(func.count(func.distinct(ActivityDay.user_id)))
                   .where(ActivityDay.day > today - timedelta(days=7))) or 0
    mau = s.scalar(select(func.count(func.distinct(ActivityDay.user_id)))
                   .where(ActivityDay.day > today - timedelta(days=30))) or 0
    new_today = s.scalar(select(func.count()).select_from(User).where(
        User.created_at >= ist_day_start())) or 0
    return {"dau": dau, "wau": wau, "mau": mau, "new_today": new_today}


def cohort(s: Session, since: datetime) -> list[tuple[str, datetime]]:
    return [(uid, aware(created)) for uid, created in s.execute(
        select(User.id, User.created_at).where(User.created_at >= since, User.kind != "deleted")).all()]


def active_days(s: Session, ids: list[str]) -> dict[str, set]:
    out: dict[str, set] = {i: set() for i in ids}
    for chunk in range(0, len(ids), 500):
        part = ids[chunk:chunk + 500]
        for uid, day in s.execute(select(ActivityDay.user_id, ActivityDay.day)
                                  .where(ActivityDay.user_id.in_(part))).all():
            out[uid].add(day)
    return out

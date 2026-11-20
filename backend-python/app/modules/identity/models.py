"""Identity module tables: users, app sessions and daily activity.

Until phone sign-in ships (M2), each app install gets a pseudonymous device account: no
phone and no name beyond a generated one. Sign-in will attach a verified phone to the same
account, so points and calls carry over.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    # "device" (pseudonymous, before sign-in) or "legacy" (prototype phone accounts).
    kind: Mapped[str] = mapped_column(String(16), default="device")
    phone: Mapped[str | None] = mapped_column(String(32), index=True)
    display_name: Mapped[str] = mapped_column(String(80), default="Forecaster")
    handle: Mapped[str | None] = mapped_column(String(40), default=None)
    # Self-declared state (ISO 3166-2:IN code), used only for regional feature switches.
    region: Mapped[str | None] = mapped_column(String(4))
    # Preset avatar key (no uploaded photos are stored).
    avatar: Mapped[str | None] = mapped_column(String(24))
    # Invite tracking: this user's own code, and the user whose code they joined with.
    invite_code: Mapped[str | None] = mapped_column(String(16), unique=True)
    invited_by: Mapped[str | None] = mapped_column(String(40), index=True)
    blocked: Mapped[bool] = mapped_column(Boolean, default=False)
    # Moderator sanction: no calls or comments until this time.
    suspended_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    warnings: Mapped[int] = mapped_column(Integer, default=0)
    # Voluntary self-exclusion (spec s.2 safeguards). Can be extended, never shortened.
    excluded_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AppSession(Base):
    """Bearer token for the app. Only a SHA-256 of the token is stored."""
    __tablename__ = "user_sessions"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ActivityDay(Base):
    """One row per user per Indian day they used the app: pseudonymous DAU/MAU counts."""
    __tablename__ = "activity_days"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    day: Mapped[date] = mapped_column(Date, primary_key=True, index=True)

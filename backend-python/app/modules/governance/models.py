"""Governance tables: admin accounts, admin sessions, the audit log and error counts."""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.modules.identity.models import utcnow


class AdminUser(Base):
    __tablename__ = "admin_users"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    email: Mapped[str] = mapped_column(String(160), unique=True)
    name: Mapped[str] = mapped_column(String(80))
    password_hash: Mapped[str] = mapped_column(Text)
    # Base32 TOTP secret. Two-factor sign-in is mandatory: an admin without an enrolled
    # secret can only reach the enrolment page.
    totp_secret: Mapped[str | None] = mapped_column(String(64))
    totp_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    # Last accepted TOTP time step, so a code can't be replayed.
    totp_last_step: Mapped[int | None] = mapped_column(Integer)
    roles: Mapped[list] = mapped_column(JSON, default=list)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=True)
    failed_logins: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AdminSession(Base):
    """Cookie session. Only a SHA-256 of the token is stored. `verified` turns true after the
    second factor; until then the session can only complete two-factor sign-in."""
    __tablename__ = "admin_sessions"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    admin_id: Mapped[str] = mapped_column(ForeignKey("admin_users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    ip: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AdminAudit(Base):
    """Append-only record of every admin action (spec s.3; SOW 3.8). A database trigger
    rejects UPDATE and DELETE on Postgres."""
    __tablename__ = "admin_audit"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    admin_id: Mapped[str | None] = mapped_column(String(40), index=True)
    admin_email: Mapped[str | None] = mapped_column(String(160))
    roles: Mapped[list] = mapped_column(JSON, default=list)
    action: Mapped[str] = mapped_column(String(60), index=True)
    target_type: Mapped[str | None] = mapped_column(String(30))
    target_id: Mapped[str | None] = mapped_column(String(60), index=True)
    before: Mapped[dict | None] = mapped_column(JSON)
    after: Mapped[dict | None] = mapped_column(JSON)
    ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(300))
    correlation_id: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class ErrorDay(Base):
    """Server error counts per Indian day and status class, for the error-trend report."""
    __tablename__ = "error_days"

    day: Mapped[date] = mapped_column(Date, primary_key=True)
    kind: Mapped[str] = mapped_column(String(8), primary_key=True)
    count: Mapped[int] = mapped_column(Integer, default=0)

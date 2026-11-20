"""Compliance module tables: election quiet periods and the grievance portal."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.modules.identity.models import utcnow


class QuietPeriod(Base):
    """While active, election-sensitive questions about these states hide their live chance
    and drop out of the public sentiment dashboard (spec s.6; SOW 4.3.2 to 4.3.5)."""
    __tablename__ = "quiet_periods"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    label: Mapped[str] = mapped_column(String(120))
    # Comma-separated state codes, or "*" for every state.
    states: Mapped[str] = mapped_column(String(200))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    hide_sentiment: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[str | None] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Grievance(Base):
    """A complaint raised in the app (IT Rules 2021 r.3(2); DPDP Act s.13). Acknowledge
    within 24 hours, resolve within 15 days."""
    __tablename__ = "grievances"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    # Short reference shown to the user.
    ref: Mapped[str] = mapped_column(String(16), unique=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    category: Mapped[str] = mapped_column(String(24))
    subject: Mapped[str] = mapped_column(String(140))
    description: Mapped[str] = mapped_column(Text)
    question_id: Mapped[str | None] = mapped_column(String(40))
    # The user allows support to look at their own activity for this ticket only (SOW 3.5.7).
    support_review_consent: Mapped[bool] = mapped_column(Boolean, default=False)
    # open -> in_progress -> resolved | rejected
    status: Mapped[str] = mapped_column(String(12), default="open", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolution: Mapped[str | None] = mapped_column(Text)
    assigned_to: Mapped[str | None] = mapped_column(String(40))


class GrievanceNote(Base):
    __tablename__ = "grievance_notes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    grievance_id: Mapped[str] = mapped_column(ForeignKey("grievances.id"), index=True)
    admin_id: Mapped[str | None] = mapped_column(String(40))
    note: Mapped[str] = mapped_column(Text)
    # Shown to the user in the ticket's status, or internal only.
    visible_to_user: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

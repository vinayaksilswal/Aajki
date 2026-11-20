"""Forecasts module tables: topics, questions, calls, settlements and disputes.

The questions table keeps its prototype name ("polls") so live data migrates in place; the
Python and API vocabulary follows the spec (question, outcome, call). Points move only
through the ledger module; a call records which ledger transaction committed its points.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (Boolean, DateTime, ForeignKey, Index, Integer, JSON, String, Text,
                        UniqueConstraint)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.modules.identity.models import utcnow

CATEGORIES: dict[str, str] = {
    "elections": "Elections",
    "markets": "Markets",
    "sports": "Sports",
    "policy": "Policy",
    "world": "World",
    "community": "Community",
}

# Stored lifecycle. "scheduled", "open" and "closed" are derived from the publish window
# at read time (see service.effective_status), so no background job is needed to flip them.
STORED_STATUSES = ("draft", "published", "paused", "voided", "settled")


class Topic(Base):
    __tablename__ = "topics"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    slug: Mapped[str] = mapped_column(String(120))
    title: Mapped[str] = mapped_column(String(200))
    short_label: Mapped[str | None] = mapped_column(String(120))
    blurb: Mapped[str | None] = mapped_column(Text)
    image_url: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(40), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Question(Base):
    __tablename__ = "polls"
    __table_args__ = (Index("ix_polls_status_closes_at", "status", "closes_at"),)

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    slug: Mapped[str] = mapped_column(String(160))
    category: Mapped[str] = mapped_column(String(40), index=True)
    title: Mapped[str] = mapped_column("question", Text)
    description: Mapped[str | None] = mapped_column(Text)
    image_url: Mapped[str | None] = mapped_column(Text)
    # [{"key": "yes", "label": "India wins"}, {"key": "no", "label": "India doesn't win"}]
    outcomes: Mapped[list] = mapped_column("options", JSON, default=list)
    topic_id: Mapped[str | None] = mapped_column(ForeignKey("topics.id"), index=True)
    trending: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(16), default="draft")
    opens_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closes_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolution_source_url: Mapped[str | None] = mapped_column(Text)
    resolution_rule: Mapped[str | None] = mapped_column(Text)
    election_sensitive: Mapped[bool] = mapped_column(Boolean, default=False)
    # Indian state (or "national") an election-sensitive question is about; quiet periods
    # for that state withhold its live chance (spec s.6, SOW 4.3.2).
    election_state: Mapped[str | None] = mapped_column(String(40))
    # When drafted from a ticker headline: the context it came from.
    source_headline: Mapped[str | None] = mapped_column(Text)
    source_link: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=utcnow,
                                                        onupdate=utcnow)


class Call(Base):
    """One user's call on one question: the outcome they chose and the points committed."""
    __tablename__ = "calls"
    __table_args__ = (UniqueConstraint("question_id", "user_id", name="uq_calls_question_user"),
                      Index("ix_calls_user_created", "user_id", "created_at"))

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    question_id: Mapped[str] = mapped_column(ForeignKey("polls.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    outcome_key: Mapped[str] = mapped_column(String(40))
    points: Mapped[int] = mapped_column(Integer)
    # active -> correct | incorrect | refunded
    status: Mapped[str] = mapped_column(String(12), default="active")
    # Points released back to the user at settlement (correct calls and refunds).
    released: Mapped[int | None] = mapped_column(Integer)
    commit_txn_id: Mapped[str] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    settled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Settlement(Base):
    """A proposed result and its two-person decision (spec s.3, s.6).

    proposed -> approved | rejected; an approved result can later be superseded by a
    corrected one (status "superseded"), which reverses its ledger entries.
    """
    __tablename__ = "settlements"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    question_id: Mapped[str] = mapped_column(ForeignKey("polls.id"), index=True)
    # An outcome key, or "void" for a cancelled or abandoned event.
    result: Mapped[str] = mapped_column(String(40))
    source_url: Mapped[str | None] = mapped_column(Text)
    note: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(12), default="proposed")
    # Set when this proposal corrects an earlier approved result.
    corrects_id: Mapped[str | None] = mapped_column(String(40))
    proposed_by: Mapped[str] = mapped_column(String(40))
    proposed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    decided_by: Mapped[str | None] = mapped_column(String(40))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_note: Mapped[str | None] = mapped_column(Text)
    # What was applied: the outcome, or "void" (also when the rules forced a void).
    applied_result: Mapped[str | None] = mapped_column(String(40))
    applied_reason: Mapped[str | None] = mapped_column(Text)
    dispute_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Dispute(Base):
    """A user's challenge to an approved result, raised inside the dispute window."""
    __tablename__ = "settlement_disputes"
    __table_args__ = (UniqueConstraint("settlement_id", "user_id", name="uq_disputes_settlement_user"),)

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    settlement_id: Mapped[str] = mapped_column(ForeignKey("settlements.id"), index=True)
    question_id: Mapped[str] = mapped_column(String(40), index=True)
    user_id: Mapped[str] = mapped_column(String(40))
    reason: Mapped[str] = mapped_column(Text)
    evidence_url: Mapped[str | None] = mapped_column(Text)
    # open -> upheld | dismissed
    status: Mapped[str] = mapped_column(String(12), default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    decided_by: Mapped[str | None] = mapped_column(String(40))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_note: Mapped[str | None] = mapped_column(Text)

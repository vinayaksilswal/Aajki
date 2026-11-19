"""Forecasts module tables: topics, questions and (pre-ledger) participation records.

Table names are kept from the prototype ("polls", "votes") so live data migrates in place;
the Python and API vocabulary follows the spec (question, outcome, call).
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, JSON, String, Text
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
    # When drafted from a ticker headline: the context it came from.
    source_headline: Mapped[str | None] = mapped_column(Text)
    source_link: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=utcnow,
                                                        onupdate=utcnow)


class Vote(Base):
    """Prototype participation record (one row per reaction). Calls with committed points
    and the double-entry ledger replace this in M3; until then it feeds the consensus."""
    __tablename__ = "votes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    question_id: Mapped[str] = mapped_column("poll_id", ForeignKey("polls.id", ondelete="CASCADE"),
                                             index=True)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), index=True)
    outcome_key: Mapped[str] = mapped_column("option_key", String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

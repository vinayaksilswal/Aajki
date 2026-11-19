"""News module tables: headlines for the in-app context ticker."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.modules.identity.models import utcnow


class NewsItem(Base):
    __tablename__ = "news_items"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    category: Mapped[str] = mapped_column(String(40), index=True)
    title: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(200))
    link: Mapped[str] = mapped_column(Text)
    # sha256 of the link: links are long, so dedupe on a fixed-width unique key.
    link_hash: Mapped[str] = mapped_column(String(64), unique=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    # Set when an admin drafts a question from this headline; the ticker then links to it.
    question_id: Mapped[str | None] = mapped_column(ForeignKey("polls.id", ondelete="SET NULL"))
    hidden: Mapped[bool] = mapped_column(Boolean, default=False)

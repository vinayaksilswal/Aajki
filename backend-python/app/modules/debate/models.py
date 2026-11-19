"""Debate module tables. Replies, attachments, reports and blocks arrive in M4."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.modules.identity.models import utcnow


class Comment(Base):
    __tablename__ = "comments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    question_id: Mapped[str] = mapped_column("poll_id", ForeignKey("polls.id", ondelete="CASCADE"),
                                             index=True)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    author_name: Mapped[str] = mapped_column(String(80), default="User")
    body: Mapped[str] = mapped_column(Text)
    hidden: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

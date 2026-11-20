"""Debate module tables: comments and replies, reports, user blocks and moderation actions.

Attachments (photo, video up to 20 s, voice note) are not accepted yet: the spec requires each
to pass automated screening before anyone sees it, and no screening vendor or object storage
is configured. The API refuses attachments until both are.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.modules.identity.models import utcnow


class Comment(Base):
    __tablename__ = "comments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    question_id: Mapped[str] = mapped_column("poll_id", ForeignKey("polls.id", ondelete="CASCADE"),
                                             index=True)
    # Replies point at a top-level comment (one level of replies).
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("comments.id"), index=True)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), index=True)
    author_name: Mapped[str] = mapped_column(String(80), default="User")
    body: Mapped[str] = mapped_column(Text)
    # visible | held (auto-hidden after reports, awaiting review) | removed | deleted (by author)
    status: Mapped[str] = mapped_column(String(10), default="visible", index=True)
    removed_reason: Mapped[str | None] = mapped_column(String(24))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CommentReport(Base):
    __tablename__ = "comment_reports"
    __table_args__ = (UniqueConstraint("comment_id", "reporter_id", name="uq_comment_reports_comment_reporter"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    comment_id: Mapped[int] = mapped_column(ForeignKey("comments.id"), index=True)
    reporter_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    reason: Mapped[str] = mapped_column(String(16))
    note: Mapped[str | None] = mapped_column(String(280))
    # open -> actioned | dismissed
    status: Mapped[str] = mapped_column(String(10), default="open", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    handled_by: Mapped[str | None] = mapped_column(String(40))
    handled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class UserBlock(Base):
    """The blocker no longer sees the blocked user's comments."""
    __tablename__ = "user_blocks"

    blocker_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    blocked_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ModerationAction(Base):
    """Every moderation decision with its reason code (spec s.3; IT Rules record keeping)."""
    __tablename__ = "moderation_actions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    admin_id: Mapped[str] = mapped_column(String(40))
    # remove | restore | dismiss | warn | suspend | unsuspend
    action: Mapped[str] = mapped_column(String(12))
    reason_code: Mapped[str] = mapped_column(String(24))
    comment_id: Mapped[int | None] = mapped_column(Integer, index=True)
    user_id: Mapped[str | None] = mapped_column(String(40), index=True)
    note: Mapped[str | None] = mapped_column(Text)
    # Hours from the first open report to this action (report-handling time).
    handling_hours: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

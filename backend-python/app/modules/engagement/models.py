"""Engagement module tables: daily check-ins and the daily quiz (spec s.2, SOW 2.8)."""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.modules.identity.models import utcnow


class CheckIn(Base):
    __tablename__ = "checkins"
    __table_args__ = (UniqueConstraint("user_id", "day", name="uq_checkins_user_day"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    day: Mapped[date] = mapped_column(Date)
    streak: Mapped[int] = mapped_column(Integer)
    # Points credited (0 when the daily reward cap was already reached).
    reward: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Quiz(Base):
    """One short quiz per Indian day, set by Content Ops."""
    __tablename__ = "quizzes"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    day: Mapped[date] = mapped_column(Date, unique=True)
    question: Mapped[str] = mapped_column(Text)
    # [{"key": "a", "label": "..."}, ...] (2 to 4 options)
    options: Mapped[list] = mapped_column(JSON)
    correct_key: Mapped[str] = mapped_column(String(8))
    explanation: Mapped[str | None] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[str | None] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class QuizAnswer(Base):
    __tablename__ = "quiz_answers"
    __table_args__ = (UniqueConstraint("quiz_id", "user_id", name="uq_quiz_answers_quiz_user"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    quiz_id: Mapped[str] = mapped_column(ForeignKey("quizzes.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    answer_key: Mapped[str] = mapped_column(String(8))
    correct: Mapped[bool] = mapped_column(Boolean)
    reward: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

"""Standing module tables: the badge catalogue (status rewards only, spec s.2)."""
from __future__ import annotations

from sqlalchemy import Boolean, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

# What a badge measures. Earned badges are computed from the user's record, never stored,
# so a corrected result or a changed threshold is reflected at once.
BADGE_RULES = {
    "calls": "Calls made",
    "correct": "Correct calls",
    "streak": "Check-in streak (days)",
    "lifetime": "Lifetime points earned",
    "invites": "Friends who joined",
}


class Badge(Base):
    __tablename__ = "badges"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str] = mapped_column(String(60))
    description: Mapped[str] = mapped_column(Text)
    emoji: Mapped[str] = mapped_column(String(8))
    rule: Mapped[str] = mapped_column(String(16))
    threshold: Mapped[int] = mapped_column(Integer)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort: Mapped[int] = mapped_column(Integer, default=0)

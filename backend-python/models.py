"""ORM models. JSON columns (JSONB on Postgres) hold nested option/story/board data so the
admin can manage everything without a sprawl of tables. Votes/comments/users are first-class
so the admin can see the audience and moderate.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import String, Integer, Boolean, DateTime, ForeignKey, JSON, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    phone: Mapped[str] = mapped_column(String(32), index=True)
    display_name: Mapped[str] = mapped_column(String(80), default="Player")
    handle: Mapped[str | None] = mapped_column(String(40), default=None)
    coins: Mapped[int] = mapped_column(Integer, default=100)
    blocked: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    votes: Mapped[list["Vote"]] = relationship(back_populates="user")


class Topic(Base):
    __tablename__ = "topics"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    slug: Mapped[str] = mapped_column(String(120))
    title: Mapped[str] = mapped_column(String(200))
    short_label: Mapped[str | None] = mapped_column(String(120))
    blurb: Mapped[str | None] = mapped_column(Text)
    image_url: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(40), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    polls: Mapped[list["Poll"]] = relationship(back_populates="topic")


class Poll(Base):
    __tablename__ = "polls"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    slug: Mapped[str] = mapped_column(String(160))
    category: Mapped[str] = mapped_column(String(40), index=True)
    question: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    image_url: Mapped[str | None] = mapped_column(Text)
    display_kind: Mapped[str] = mapped_column(String(20), default="binary")
    # options: [{"key": "yes", "label": "Yes", "emoji": null, "base_votes": 10}, ...]
    options: Mapped[list] = mapped_column(JSON, default=list)
    topic_id: Mapped[str | None] = mapped_column(ForeignKey("topics.id"), index=True)
    trending: Mapped[bool] = mapped_column(Boolean, default=False)
    is_prediction: Mapped[bool] = mapped_column(Boolean, default=False)
    reward_coins: Mapped[int] = mapped_column(Integer, default=5)
    status: Mapped[str] = mapped_column(String(16), default="open")  # open | closed
    like_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    topic: Mapped[Topic | None] = relationship(back_populates="polls")
    votes: Mapped[list["Vote"]] = relationship(back_populates="poll", cascade="all, delete-orphan")
    comments: Mapped[list["Comment"]] = relationship(back_populates="poll", cascade="all, delete-orphan")


class Vote(Base):
    __tablename__ = "votes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    poll_id: Mapped[str] = mapped_column(ForeignKey("polls.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), index=True)
    option_key: Mapped[str] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    poll: Mapped[Poll] = relationship(back_populates="votes")
    user: Mapped[User | None] = relationship(back_populates="votes")


class Comment(Base):
    __tablename__ = "comments"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    poll_id: Mapped[str] = mapped_column(ForeignKey("polls.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    author_name: Mapped[str] = mapped_column(String(80), default="User")
    body: Mapped[str] = mapped_column(Text)
    hidden: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    poll: Mapped[Poll] = relationship(back_populates="comments")


class Story(Base):
    __tablename__ = "stories"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    desk: Mapped[str] = mapped_column(String(60))
    hook: Mapped[str] = mapped_column(Text)
    # data: {cover, context[], questions[], share_url, path, ...}
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class Board(Base):
    __tablename__ = "boards"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    title: Mapped[str] = mapped_column(String(120))
    data: Mapped[dict] = mapped_column(JSON, default=dict)  # full board object
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(60), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON, default=dict)

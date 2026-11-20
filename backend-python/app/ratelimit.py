"""Fixed-window rate limits kept in the database, so every serverless instance shares them.

Counts are written in their own short transaction: a request that later fails still counts,
which is what abuse limits (OTP, login, comment floods) need. Subjects are hashed, so the
table holds no raw IP addresses.
"""
from __future__ import annotations

import hashlib
import os
import random
import time
from datetime import datetime, timedelta, timezone

from fastapi import Request
from sqlalchemy import DateTime, Integer, String, delete
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Mapped, mapped_column

from app.config import get_settings
from app.db import Base, session_scope
from app.errors import AppError


class RateLimitCounter(Base):
    __tablename__ = "rate_limits"

    key: Mapped[str] = mapped_column(String(160), primary_key=True)
    count: Mapped[int] = mapped_column(Integer, default=0)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


def client_ip(request: Request) -> str:
    """The caller's address. Proxy headers are trusted only behind a known proxy (Vercel
    overwrites them; elsewhere set TRUST_PROXY_HEADERS=true only behind your own proxy)."""
    if get_settings().trust_proxy_headers or os.environ.get("VERCEL"):
        real = request.headers.get("x-real-ip") or request.headers.get("x-forwarded-for", "")
        first = real.split(",")[0].strip()
        if first:
            return first
    return request.client.host if request.client else "unknown"


def subject_hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()[:24]


def hit(name: str, subject: str, limit: int, window_seconds: int, message: str) -> None:
    """Count one event; raise 429 once `limit` events happen inside the window."""
    now = time.time()
    bucket = int(now // window_seconds)
    key = f"{name}:{subject_hash(subject)}:{bucket}"
    expires = datetime.fromtimestamp((bucket + 1) * window_seconds, tz=timezone.utc)
    with session_scope() as s:
        insert = pg_insert if s.bind.dialect.name == "postgresql" else sqlite_insert
        stmt = (insert(RateLimitCounter).values(key=key, count=1, expires_at=expires)
                .on_conflict_do_update(index_elements=[RateLimitCounter.key],
                                       set_={"count": RateLimitCounter.count + 1})
                .returning(RateLimitCounter.count))
        count = s.execute(stmt).scalar_one()
        if random.random() < 0.01:  # occasional cleanup of finished windows
            s.execute(delete(RateLimitCounter).where(
                RateLimitCounter.expires_at < datetime.now(timezone.utc) - timedelta(hours=1)))
    if count > limit:
        retry = max(1, int((bucket + 1) * window_seconds - now))
        raise AppError(429, "RATE_LIMITED", message, {"retry_after_seconds": retry})

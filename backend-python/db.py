"""Database layer. Reads DATABASE_URL (Postgres/MySQL/SQLite) and exposes a session.

Set DATABASE_URL as an env var (locally in backend-python/.env, in prod in the Vercel
project settings). With no DATABASE_URL it falls back to a local SQLite file for dev.
"""
from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).with_name(".env"))
except Exception:
    pass


def _normalize(url: str) -> str:
    # Pick a driver SQLAlchemy understands, keeping libpq params (sslmode, channel_binding).
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://"):]
    if url.startswith("mysql://"):
        return "mysql+pymysql://" + url[len("mysql://"):]
    return url


DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
if DATABASE_URL:
    ENGINE_URL = _normalize(DATABASE_URL)
    _connect_args = {}
else:
    ENGINE_URL = "sqlite:///" + str(Path(__file__).with_name("aajki.db"))
    _connect_args = {"check_same_thread": False}

# pool_pre_ping keeps serverless connections healthy; modest pool for Neon's pooler.
engine = create_engine(ENGINE_URL, connect_args=_connect_args, pool_pre_ping=True,
                       pool_size=3, max_overflow=2, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


class Base(DeclarativeBase):
    pass


def get_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

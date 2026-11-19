"""Database engine and sessions.

Schema is owned by Alembic migrations (backend-python/alembic); the app never creates or
alters tables at startup. With no DATABASE_URL in development, a local SQLite file is used.
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import MetaData, create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import BACKEND_DIR, get_settings

# Deterministic constraint names so migrations can reference them.
NAMING = {
    "ix": "ix_%(table_name)s_%(column_0_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING)


def normalize_url(url: str) -> str:
    """Pick a driver SQLAlchemy understands, keeping libpq params (sslmode, channel_binding)."""
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


def database_url() -> str:
    url = get_settings().database_url.strip()
    if url:
        return normalize_url(url)
    return "sqlite:///" + str(BACKEND_DIR / "local.db")


def _make_engine():
    url = database_url()
    if url.startswith("sqlite"):
        return create_engine(url, connect_args={"check_same_thread": False}, future=True)
    connect_args = {}
    host = make_url(url).host or ""
    if "pooler" in host:
        # Transaction-mode poolers (Neon, PgBouncer) can't keep server-side prepared statements.
        connect_args["prepare_threshold"] = None
    # Small pool: serverless instances are many and short-lived.
    return create_engine(url, connect_args=connect_args, pool_pre_ping=True, pool_size=3,
                         max_overflow=2, pool_recycle=300, future=True)


engine = _make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


@contextmanager
def session_scope() -> Iterator[Session]:
    """A unit of work: commits on success, rolls back on any error."""
    s = SessionLocal()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()

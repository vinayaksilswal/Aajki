"""Test harness: a throwaway SQLite database built by the real Alembic migrations.

Environment is pinned before the app is imported, so a developer's backend-python/.env
(which may point at the live database) is never used by tests.
"""
from __future__ import annotations

import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="bf-tests-"))
os.environ.update({
    "APP_ENV": "test",
    "DATABASE_URL": f"sqlite:///{(_TMP / 'test.db').as_posix()}",
    "ADMIN_PASSWORD": "",
    "CRON_SECRET": "",
    "ALLOWED_ORIGINS": "",
    "ELECTION_QUIET_PERIOD": "false",
})

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import delete  # noqa: E402

from app.config import BACKEND_DIR, get_settings  # noqa: E402
from app.db import SessionLocal, database_url  # noqa: E402
from app.ids import new_id  # noqa: E402
from app.modules.debate.models import Comment  # noqa: E402
from app.modules.forecasts.models import Question, Topic, Vote  # noqa: E402
from app.modules.identity.models import User  # noqa: E402
from app.modules.news import ingest  # noqa: E402
from app.modules.news.models import NewsItem  # noqa: E402
from app.modules.sentiment import service as sentiment  # noqa: E402

assert database_url().startswith("sqlite:///") and "bf-tests-" in database_url(), \
    "tests must never run against a real database"

ORIGIN = "http://testserver"
NOW = datetime.now(timezone.utc)


def alembic_config() -> Config:
    return Config(str(BACKEND_DIR / "alembic.ini"))


@pytest.fixture(scope="session", autouse=True)
def _schema():
    command.upgrade(alembic_config(), "head")


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    with SessionLocal() as s:
        for model in (Vote, Comment, NewsItem, Question, Topic, User):
            s.execute(delete(model))
        s.commit()
    sentiment.clear_cache()

    def _no_network(*_a, **_k):
        raise RuntimeError("tests must not fetch live news; patch ingest.urllib.request.urlopen")
    monkeypatch.setattr(ingest.urllib.request, "urlopen", _no_network)

    st = get_settings()
    for key in ("admin_password", "cron_secret", "election_quiet_period", "app_env"):
        monkeypatch.setattr(st, key, getattr(st, key))  # restored after each test
    yield


@pytest.fixture
def client():
    from app.main import create_app
    return TestClient(create_app())


@pytest.fixture
def settings():
    return get_settings()


def make_question(**kw) -> str:
    """Insert a question directly. Defaults: a published question, open now."""
    qid = kw.pop("id", None) or new_id("q")
    votes = kw.pop("votes", {})
    fields = dict(
        slug=qid, category="elections", title="Will turnout in the test bypoll cross 60 percent?",
        outcomes=[{"key": "yes", "label": "Turnout ≥ 60%"}, {"key": "no", "label": "Turnout < 60%"}],
        status="published", opens_at=NOW - timedelta(hours=1), closes_at=NOW + timedelta(days=2),
        resolution_source_url="https://results.eci.gov.in/", trending=False,
        resolution_rule="Resolves Yes if the ECI's final turnout figure is 60% or higher.",
        election_sensitive=False)
    fields.update(kw)
    with SessionLocal() as s:
        s.add(Question(id=qid, **fields))
        s.flush()
        for key, n in votes.items():
            s.add_all(Vote(question_id=qid, outcome_key=key) for _ in range(n))
        s.commit()
    return qid


def make_news(**kw) -> str:
    nid = kw.pop("id", None) or new_id("news")
    link = kw.pop("link", f"https://example.com/{nid}")
    fields = dict(category="markets", title="Sensex closes higher as banks rally in late trade",
                  source="Example Times", link=link, link_hash=nid, published_at=NOW,
                  fetched_at=NOW, hidden=False)
    fields.update(kw)
    with SessionLocal() as s:
        s.add(NewsItem(id=nid, **fields))
        s.commit()
    return nid

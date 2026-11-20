"""Test harness: a throwaway SQLite database built by the real Alembic migrations.

Environment is pinned before the app is imported, so a developer's backend-python/.env
(which may point at the live database) is never used by tests.
"""
from __future__ import annotations

import os
import secrets
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
    "SENTRY_DSN": "",
})
os.environ.pop("VERCEL", None)

import pyotp  # noqa: E402
import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import delete  # noqa: E402

import app.models  # noqa: E402,F401  (registers every table)
from app.config import BACKEND_DIR, get_settings  # noqa: E402
from app.db import Base, SessionLocal, database_url  # noqa: E402
from app.ids import new_id  # noqa: E402
from app.modules.forecasts.models import Call, Question  # noqa: E402
from app.modules.governance import auth  # noqa: E402
from app.modules.governance.models import AdminSession, AdminUser  # noqa: E402
from app.modules.identity.models import User  # noqa: E402
from app.modules.news import ingest  # noqa: E402
from app.modules.news.models import NewsItem  # noqa: E402
from app.modules.policy import service as policy  # noqa: E402
from app.modules.sentiment import public as public_sentiment  # noqa: E402
from app.modules.sentiment import service as sentiment  # noqa: E402

assert database_url().startswith("sqlite:///") and "bf-tests-" in database_url(), \
    "tests must never run against a real database"

ORIGIN = "http://testserver"
NOW = datetime.now(timezone.utc)
KEEP = {"badges", "alembic_version"}       # seeded by the migration
ALL_ROLES_BUT_APPROVER = ["super_admin", "content_ops", "settlement_officer", "moderator", "compliance"]


def alembic_config() -> Config:
    return Config(str(BACKEND_DIR / "alembic.ini"))


@pytest.fixture(scope="session", autouse=True)
def _schema():
    command.upgrade(alembic_config(), "head")


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    with SessionLocal() as s:
        for table in reversed(Base.metadata.sorted_tables):
            if table.name not in KEEP:
                s.execute(delete(table))
        s.commit()
    sentiment.clear_cache()
    public_sentiment.clear_cache()
    policy.clear_cache()

    def _no_network(*_a, **_k):
        raise RuntimeError("tests must not fetch live news; patch ingest.urllib.request.urlopen")
    monkeypatch.setattr(ingest.urllib.request, "urlopen", _no_network)

    st = get_settings()
    for key in ("admin_password", "admin_user", "cron_secret", "election_quiet_period", "app_env",
                "daily_call_cap", "dispute_window_hours"):
        monkeypatch.setattr(st, key, getattr(st, key))  # restored after each test
    yield


@pytest.fixture
def client():
    from app.main import create_app
    return TestClient(create_app())


@pytest.fixture
def settings():
    return get_settings()


# ----------------------------------------------------------------------------- admins

def make_admin(roles: list[str], email: str | None = None, password: str = "Str0ngPassword!") -> AdminUser:
    """An enrolled admin (password + TOTP), ready to sign in."""
    with SessionLocal() as s:
        a = AdminUser(id=new_id("adm"), email=email or f"{new_id('a').lower()}@example.in", name="Test Admin",
                      password_hash=auth.hash_password(password), roles=roles, totp_secret=pyotp.random_base32(),
                      totp_enabled=True, must_change_password=False)
        s.add(a)
        s.commit()
        s.refresh(a)
        s.expunge(a)
        return a


def login(client: TestClient, roles: list[str]) -> AdminUser:
    """Sign a test client in as a fresh admin with these roles (session already 2FA-verified)."""
    a = make_admin(roles)
    token = secrets.token_urlsafe(32)
    with SessionLocal() as s:
        s.add(AdminSession(id=new_id("ases"), admin_id=a.id, token_hash=auth._hash_token(token), verified=True,
                           expires_at=datetime.now(timezone.utc) + timedelta(hours=1)))
        s.commit()
    client.cookies.set(auth.COOKIE, token, path="/admin")
    return a


@pytest.fixture
def admin_client(client):
    """Signed in with every role except Settlement Approver (no one holds both settlement roles)."""
    login(client, ALL_ROLES_BUT_APPROVER)
    return client


POST = {"headers": {"Origin": ORIGIN}, "follow_redirects": False}


# ----------------------------------------------------------------------------- app users

def new_user(client: TestClient) -> dict:
    """A device account; returns Authorization headers."""
    r = client.post("/v1/session", json={})
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def user_id(client: TestClient, headers: dict) -> str:
    return client.get("/v1/me", headers=headers).json()["id"]


def call(client: TestClient, headers: dict, qid: str, outcome: str = "yes", points: int = 100,
         key: str | None = None):
    return client.post(f"/v1/questions/{qid}/calls", json={"outcome_key": outcome, "points": points},
                       headers={**headers, "Idempotency-Key": key or new_id("k")})


# ----------------------------------------------------------------------------- content

def make_question(**kw) -> str:
    """Insert a question directly. Defaults: a published question, open now.
    `votes={"yes": 3}` adds that many calls of 10 points from fresh users (no ledger
    movement: for read-model tests only)."""
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
            for _ in range(n):
                uid = new_id("usr")
                s.add(User(id=uid, kind="device", display_name="Forecaster"))
                s.flush()
                s.add(Call(id=new_id("call"), question_id=qid, user_id=uid, outcome_key=key, points=10,
                           status="active", commit_txn_id="seed"))
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

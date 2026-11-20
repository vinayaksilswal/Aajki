"""Admin panel: sign-in with two-factor, roles, CSRF, audit, and the create -> publish -> feed flow."""
from __future__ import annotations

import re
from datetime import timedelta

import pyotp
import pytest
from sqlalchemy import select

from app.clock import IST
from app.db import SessionLocal
from app.modules.forecasts.models import Question
from app.modules.governance.models import AdminAudit, AdminUser
from tests.conftest import NOW, POST, login, make_admin, make_question


def ist_input(dt) -> str:
    return dt.astimezone(IST).strftime("%Y-%m-%dT%H:%M")


def form(**kw) -> dict:
    data = {"title": "Will the Bihar bypoll turnout cross 58 percent?", "category": "elections",
            "outcome_yes": "Turnout ≥ 58%", "outcome_no": "Turnout < 58%",
            "closes_at": ist_input(NOW + timedelta(days=3)),
            "resolution_source_url": "https://results.eci.gov.in/",
            "resolution_rule": "Resolves Yes if the ECI's provisional turnout is 58% or more.",
            "election_sensitive": "1"}
    data.update(kw)
    return data


# ------------------------------------------------------------------ sign-in

def test_every_admin_page_requires_sign_in(client):
    for path in ("/admin/dashboard", "/admin/questions", "/admin/audit", "/admin/admins"):
        r = client.get(path, follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"] == "/admin/login"


def test_bootstrap_creates_the_first_super_admin_then_requires_2fa(client, settings):
    settings.admin_user, settings.admin_password = "owner@example.in", "Bootstrap-Pass-2026"
    r = client.post("/admin/login", data={"email": "owner@example.in", "password": "wrong"}, **POST)
    assert r.status_code == 401
    r = client.post("/admin/login", data={"email": "owner@example.in", "password": "Bootstrap-Pass-2026"}, **POST)
    assert r.status_code == 303 and r.headers["location"] == "/admin/2fa/setup"
    # Not signed in until two-factor is set up.
    assert client.get("/admin/dashboard", follow_redirects=False).headers["location"] == "/admin/2fa/setup"
    page = client.get("/admin/2fa/setup").text
    secret = re.search(r"<code>([A-Z2-7]+)</code>", page).group(1)
    r = client.post("/admin/2fa/setup", data={"code": "000000"}, **POST)
    assert r.status_code == 422
    r = client.post("/admin/2fa/setup", data={"code": pyotp.TOTP(secret).now()}, **POST)
    assert r.status_code == 303
    assert client.get("/admin/dashboard").status_code == 200
    with SessionLocal() as s:
        (a,) = s.scalars(select(AdminUser)).all()
        assert a.roles == ["super_admin"] and a.totp_enabled
        actions = {x.action for x in s.scalars(select(AdminAudit)).all()}
        assert {"admin.bootstrap", "admin.2fa_enrolled"} <= actions


def test_bootstrap_login_stops_working_once_an_admin_exists(client, settings):
    make_admin(["super_admin"])
    settings.admin_user, settings.admin_password = "owner@example.in", "Bootstrap-Pass-2026"
    r = client.post("/admin/login", data={"email": "owner@example.in", "password": "Bootstrap-Pass-2026"}, **POST)
    assert r.status_code == 401


def test_password_then_totp_code_signs_in_and_a_code_cannot_be_replayed(client):
    a = make_admin(["moderator"], email="mod@example.in")
    r = client.post("/admin/login", data={"email": "mod@example.in", "password": "Str0ngPassword!"}, **POST)
    assert r.headers["location"] == "/admin/2fa"
    assert client.get("/admin/dashboard", follow_redirects=False).headers["location"] == "/admin/2fa"
    code = pyotp.TOTP(a.totp_secret).now()
    assert client.post("/admin/2fa", data={"code": code}, **POST).status_code == 303
    assert client.get("/admin/dashboard").status_code == 200
    # The same code on a new session is refused (replay).
    client.cookies.clear()
    client.post("/admin/login", data={"email": "mod@example.in", "password": "Str0ngPassword!"}, **POST)
    assert client.post("/admin/2fa", data={"code": code}, **POST).status_code == 422


def test_repeated_wrong_passwords_lock_the_account(client):
    make_admin(["moderator"], email="mod@example.in")
    for _ in range(5):
        client.post("/admin/login", data={"email": "mod@example.in", "password": "nope"}, **POST)
    r = client.post("/admin/login", data={"email": "mod@example.in", "password": "Str0ngPassword!"}, **POST)
    assert r.status_code == 429


@pytest.mark.parametrize("headers", [{}, {"Origin": "https://evil.example"},
                                     {"Referer": "https://evil.example/page"}])
def test_cross_site_posts_are_rejected(admin_client, headers):
    r = admin_client.post("/admin/questions", data=form(), headers=headers, follow_redirects=False)
    assert r.status_code == 403
    with SessionLocal() as s:
        assert s.query(Question).count() == 0


# ------------------------------------------------------------------ roles

def test_roles_limit_what_an_admin_can_do(client):
    login(client, ["moderator"])
    assert client.get("/admin/moderation").status_code == 200
    assert client.post("/admin/questions", data=form(), **POST).status_code == 403
    assert client.get("/admin/admins").status_code == 403
    assert client.get("/admin/audit").status_code == 403
    nav = client.get("/admin/dashboard").text
    assert "/admin/moderation" in nav and "/admin/admins" not in nav


def test_nobody_can_hold_both_settlement_roles(client):
    login(client, ["super_admin"])
    r = client.post("/admin/admins", data={"name": "X", "email": "x@example.in", "password": "Str0ngPassword1",
                                           "roles": ["settlement_officer", "settlement_approver"]}, **POST)
    assert r.status_code == 422
    with SessionLocal() as s:
        assert s.scalar(select(AdminUser).where(AdminUser.email == "x@example.in")) is None


def test_the_last_super_admin_cannot_be_removed(client):
    a = login(client, ["super_admin"])
    r = client.post(f"/admin/admins/{a.id}", data={"roles": ["moderator"], "active": "1"}, **POST)
    assert r.status_code == 409


# ------------------------------------------------------------------ questions

def test_create_publish_and_see_it_in_the_app_feed_with_audit(admin_client):
    r = admin_client.post("/admin/questions", data=form(), **POST)
    assert r.status_code == 303
    qid = r.headers["location"].split("/admin/questions/")[1].split("?")[0]
    assert admin_client.get("/v1/questions").json()["items"] == []          # drafts stay private

    r = admin_client.post(f"/admin/questions/{qid}/transition", data={"action": "publish"}, **POST)
    assert r.status_code == 303 and r.headers["location"].endswith("ok=published")
    feed = admin_client.get("/v1/questions").json()["items"]
    assert [q["id"] for q in feed] == [qid]
    q = feed[0]
    assert [o["label"] for o in q["outcomes"]] == ["Turnout ≥ 58%", "Turnout < 58%"]
    assert q["election_sensitive"] is True and q["category"] == "elections"
    with SessionLocal() as s:
        rows = s.scalars(select(AdminAudit).where(AdminAudit.target_id == qid).order_by(AdminAudit.id)).all()
        assert [r.action for r in rows] == ["question.create", "question.publish"]
        assert rows[1].before["status"] == "draft" and rows[1].after["status"] == "published"
        assert rows[1].ip and "content_ops" in rows[1].roles


def test_invalid_form_is_rerendered_with_errors_and_escaped_input(admin_client):
    r = admin_client.post("/admin/questions", data=form(title="<script>x</script>",
                                                         resolution_source_url="http://insecure.example"), **POST)
    assert r.status_code == 422
    assert "&lt;script&gt;x&lt;/script&gt;" in r.text and "<script>x</script>" not in r.text
    assert "Use the official source" in r.text


def test_publishing_an_incomplete_draft_explains_what_is_missing(admin_client):
    r = admin_client.post("/admin/questions", data=form(closes_at="", resolution_rule=""), **POST)
    qid = r.headers["location"].split("/admin/questions/")[1].split("?")[0]
    r = admin_client.post(f"/admin/questions/{qid}/transition", data={"action": "publish"}, **POST)
    assert r.status_code == 422
    assert "Set a closing time." in r.text and "Explain in a sentence" in r.text


def test_published_terms_cannot_be_changed_from_the_form(admin_client):
    qid = make_question()
    r = admin_client.post(f"/admin/questions/{qid}", data=form(title="Completely different question text?",
                                                               description="New context line."), **POST)
    assert r.status_code == 303
    with SessionLocal() as s:
        q = s.get(Question, qid)
        assert q.title == "Will turnout in the test bypoll cross 60 percent?"
        assert q.description == "New context line."


def test_admin_pages_are_not_cacheable_or_frameable(admin_client):
    r = admin_client.get("/admin/dashboard")
    assert r.headers["cache-control"] == "no-store"
    assert r.headers["x-frame-options"] == "DENY"
    assert "frame-ancestors 'none'" in r.headers["content-security-policy"]


def test_audit_export_is_csv_and_is_itself_audited(client):
    login(client, ["compliance"])
    r = client.get("/admin/audit.csv")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert r.text.splitlines()[0].startswith("id,created_at,admin_email")
    with SessionLocal() as s:
        assert s.scalar(select(AdminAudit).where(AdminAudit.action == "audit.export")) is not None


def test_every_admin_page_renders_for_a_full_set_of_roles(admin_client):
    qid = make_question()
    for path in ("/admin/dashboard", "/admin/questions", f"/admin/questions/{qid}", "/admin/settlements",
                 "/admin/disputes", "/admin/news", "/admin/topics", "/admin/quiz", "/admin/moderation",
                 "/admin/users", "/admin/grievances", "/admin/policy", "/admin/economy", "/admin/badges",
                 "/admin/ops", "/admin/sentiment", "/admin/admins", "/admin/audit", "/admin/password"):
        assert admin_client.get(path).status_code == 200, path

"""Admin panel: access control, CSRF guard and the create -> publish -> app feed flow."""
from __future__ import annotations

from datetime import timedelta

import pytest

from app.db import SessionLocal
from app.modules.forecasts.models import Question
from app.modules.governance.admin_views import IST
from tests.conftest import NOW, ORIGIN, make_question

POST = {"headers": {"Origin": ORIGIN}, "follow_redirects": False}


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


def test_dev_admin_is_open_without_a_password(client):
    assert client.get("/admin/questions").status_code == 200


def test_password_is_enforced_when_set(client, settings):
    settings.admin_password = "correct horse"
    r = client.get("/admin/questions")
    assert r.status_code == 401 and "Basic" in r.headers["www-authenticate"]
    assert client.get("/admin/questions", auth=("admin", "wrong")).status_code == 401
    assert client.get("/admin/questions", auth=("root", "correct horse")).status_code == 401
    assert client.get("/admin/questions", auth=("admin", "correct horse")).status_code == 200


def test_deployed_admin_without_password_is_closed_even_for_localhost_host(client, settings):
    settings.app_env = "production"
    r = client.get("/admin/questions", headers={"Host": "localhost"})
    assert r.status_code == 503


@pytest.mark.parametrize("headers", [{}, {"Origin": "https://evil.example"},
                                     {"Referer": "https://evil.example/page"}])
def test_cross_site_posts_are_rejected(client, headers):
    r = client.post("/admin/questions", data=form(), headers=headers, follow_redirects=False)
    assert r.status_code == 403
    with SessionLocal() as s:
        assert s.query(Question).count() == 0


def test_create_publish_and_see_it_in_the_app_feed(client):
    r = client.post("/admin/questions", data=form(), **POST)
    assert r.status_code == 303
    qid = r.headers["location"].split("/admin/questions/")[1].split("?")[0]
    assert client.get("/v1/questions").json()["items"] == []          # drafts stay private

    r = client.post(f"/admin/questions/{qid}/transition", data={"action": "publish"}, **POST)
    assert r.status_code == 303 and r.headers["location"].endswith("ok=published")
    feed = client.get("/v1/questions").json()["items"]
    assert [q["id"] for q in feed] == [qid]
    q = feed[0]
    assert q["title"] == "Will the Bihar bypoll turnout cross 58 percent?"
    assert [o["label"] for o in q["outcomes"]] == ["Turnout ≥ 58%", "Turnout < 58%"]
    assert q["election_sensitive"] is True and q["category"] == "elections"


def test_invalid_form_is_rerendered_with_errors_and_escaped_input(client):
    r = client.post("/admin/questions", data=form(title="<script>x</script>",
                                                   resolution_source_url="http://insecure.example"), **POST)
    assert r.status_code == 422
    assert "&lt;script&gt;x&lt;/script&gt;" in r.text and "<script>x</script>" not in r.text
    assert "Use the official source" in r.text


def test_publishing_an_incomplete_draft_explains_what_is_missing(client):
    r = client.post("/admin/questions", data=form(closes_at="", resolution_rule=""), **POST)
    qid = r.headers["location"].split("/admin/questions/")[1].split("?")[0]
    r = client.post(f"/admin/questions/{qid}/transition", data={"action": "publish"}, **POST)
    assert r.status_code == 422
    assert "Set a closing time." in r.text and "Explain in a sentence" in r.text


def test_published_terms_cannot_be_changed_from_the_form(client):
    qid = make_question()
    r = client.post(f"/admin/questions/{qid}", data=form(title="Completely different question text?",
                                                         description="New context line."), **POST)
    assert r.status_code == 303
    with SessionLocal() as s:
        q = s.get(Question, qid)
        assert q.title == "Will turnout in the test bypoll cross 60 percent?"
        assert q.description == "New context line."


def test_admin_pages_are_not_cacheable_or_frameable(client):
    r = client.get("/admin/dashboard")
    assert r.headers["cache-control"] == "no-store"
    assert r.headers["x-frame-options"] == "DENY"
    assert "frame-ancestors 'none'" in r.headers["content-security-policy"]

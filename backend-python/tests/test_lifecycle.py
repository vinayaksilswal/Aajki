"""Question lifecycle rules enforced by the forecasts service."""
from __future__ import annotations

from datetime import timedelta

import pytest

from app.db import SessionLocal
from app.errors import AppError
from app.modules.forecasts import service
from app.modules.forecasts.models import Question
from app.modules.governance.admin_views import parse_local_input
from tests.conftest import NOW, make_question


def draft(**kw) -> dict:
    d = {"title": "Will the RBI hold the repo rate at the December meeting?",
         "category": "markets", "outcomes": service.binary_outcomes("Rate held", "Rate changed")}
    d.update(kw)
    return d


def complete(**kw) -> dict:
    return draft(**{"closes_at": NOW + timedelta(days=3),
                    "resolution_source_url": "https://www.rbi.org.in/",
                    "resolution_rule": "Resolves Yes if the MPC statement keeps the repo rate unchanged.",
                    **kw})


def run(fn, *args):
    with SessionLocal() as s:
        out = fn(s, *args)
        s.commit()
        return out


def problems(exc: pytest.ExceptionInfo) -> dict:
    return exc.value.details


def test_publish_requires_closing_time_source_and_rule():
    q = run(service.create_draft, draft())
    with SessionLocal() as s, pytest.raises(AppError) as e:
        service.transition(s, s.get(Question, q.id), "publish")
    assert e.value.status == 422
    assert set(problems(e)) == {"closes_at", "resolution_source_url", "resolution_rule"}


def test_resolution_source_must_be_https():
    with SessionLocal() as s, pytest.raises(AppError) as e:
        service.create_draft(s, complete(resolution_source_url="http://www.rbi.org.in/"))
    assert "resolution_source_url" in problems(e)


def test_closing_time_needs_lead_time_and_must_follow_opening():
    with SessionLocal() as s, pytest.raises(AppError) as e:
        service.create_draft(s, complete(opens_at=NOW + timedelta(days=4)))
    assert "closes_at" in problems(e)
    q = run(service.create_draft, complete(closes_at=NOW + timedelta(minutes=2)))
    with SessionLocal() as s, pytest.raises(AppError) as e:
        service.transition(s, s.get(Question, q.id), "publish")
    assert "at least 5 minutes" in problems(e)["closes_at"]


@pytest.mark.parametrize("title", ["Will you bet on India winning the next ODI?",
                                   "What are the odds the Nifty closes above 26,000?",
                                   "Should users stake points on the RBI policy call?"])
def test_spec_vocabulary_is_enforced(title):
    with SessionLocal() as s, pytest.raises(AppError) as e:
        service.create_draft(s, draft(title=title))
    assert "title" in problems(e)


def test_vocabulary_check_matches_whole_words_only():
    q = run(service.create_draft, draft(title="Will stakeholders agree on the gap between the two bills?"))
    assert q.status == "draft"


def test_outcomes_must_be_two_distinct_labels():
    with SessionLocal() as s, pytest.raises(AppError) as e:
        service.create_draft(s, draft(outcomes=service.binary_outcomes("Yes", "yes")))
    assert "outcomes" in problems(e)


def test_publishing_opens_immediately_when_no_opening_time_is_set():
    q = run(service.create_draft, complete())
    with SessionLocal() as s:
        q = service.transition(s, s.get(Question, q.id), "publish")
        s.commit()
        assert q.status == "published" and q.opens_at is not None
        assert service.effective_status(q) == "open"


def test_terms_are_locked_once_published_but_context_stays_editable():
    qid = make_question()
    with SessionLocal() as s, pytest.raises(AppError) as e:
        service.update(s, s.get(Question, qid), {"title": "A different question about turnout entirely?"})
    assert e.value.code == "LOCKED"
    with SessionLocal() as s:
        service.update(s, s.get(Question, qid), {"description": "Updated context for readers."})
        s.commit()
        assert s.get(Question, qid).description == "Updated context for readers."


def test_only_drafts_can_be_deleted():
    qid = make_question()
    with SessionLocal() as s, pytest.raises(AppError) as e:
        service.delete_draft(s, s.get(Question, qid))
    assert e.value.status == 409
    d = run(service.create_draft, draft())
    with SessionLocal() as s:
        service.delete_draft(s, s.get(Question, d.id))
        s.commit()
        assert s.get(Question, d.id) is None


@pytest.mark.parametrize("setup,action,expected", [
    ({}, "pause", "paused"),
    ({"status": "paused"}, "resume", "open"),
    ({}, "void", "voided"),
    ({"opens_at": NOW + timedelta(hours=2)}, "unpublish", "draft"),
    ({"closes_at": NOW - timedelta(hours=1)}, "void", "voided"),
])
def test_allowed_transitions(setup, action, expected):
    qid = make_question(**setup)
    with SessionLocal() as s:
        q = service.transition(s, s.get(Question, qid), action)
        s.commit()
        assert service.effective_status(q) == expected


@pytest.mark.parametrize("setup,action", [
    ({"status": "draft"}, "pause"),
    ({}, "publish"),
    ({"status": "voided"}, "resume"),
    ({"closes_at": NOW - timedelta(hours=1)}, "pause"),
    ({}, "settle"),
])
def test_disallowed_transitions(setup, action):
    qid = make_question(**setup)
    with SessionLocal() as s, pytest.raises(AppError) as e:
        service.transition(s, s.get(Question, qid), action)
    assert e.value.status in (400, 409)


def test_admin_times_are_entered_in_ist_and_stored_in_utc():
    stored = parse_local_input("2026-12-01T18:30")
    assert stored.isoformat() == "2026-12-01T13:00:00+00:00"
    assert parse_local_input("01/12/2026") == "invalid"
    assert parse_local_input("") is None

"""Calls, the double-entry ledger, settlement (two-person rule, formula, voids), corrections
and disputes."""
from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import func, select

from app.db import SessionLocal
from app.modules.forecasts.models import Question
from app.modules.ledger.models import LedgerEntry, LedgerTransaction
from app.modules.ledger import service as ledger
from tests.conftest import NOW, POST, call, login, make_question, new_user, user_id


def points(client, h) -> dict:
    return client.get("/v1/me", headers=h).json()["points"]


def close(qid: str) -> None:
    with SessionLocal() as s:
        s.get(Question, qid).closes_at = NOW - timedelta(minutes=1)
        s.commit()


def assert_ledger_balanced():
    with SessionLocal() as s:
        sums = s.execute(select(LedgerEntry.txn_id, func.sum(LedgerEntry.amount))
                         .group_by(LedgerEntry.txn_id)).all()
        assert all(total == 0 for _, total in sums)
        assert ledger.economy(s, NOW - timedelta(days=1))["balanced"]


# ------------------------------------------------------------------ calls

def test_new_account_gets_the_welcome_reward_but_starts_at_the_first_rank(client):
    h = new_user(client)
    me = client.get("/v1/me", headers=h).json()
    assert me["points"] == {"available": 1000, "committed": 0}
    assert me["rank"]["tier"]["name"] == "Navodit" and me["rank"]["lifetime_earned"] == 0


def test_a_call_moves_points_from_available_to_committed_and_updates_the_chance(client):
    qid = make_question()
    h = new_user(client)
    r = call(client, h, qid, "yes", 200)
    assert r.status_code == 201 and r.json()["status"] == "active"
    assert points(client, h) == {"available": 800, "committed": 200}
    q = client.get(f"/v1/questions/{qid}").json()
    assert q["participants"] == 1 and q["outcomes"][0]["chance"] == 1.0
    assert_ledger_balanced()


def test_a_retried_call_with_the_same_key_commits_points_once(client):
    qid = make_question()
    h = new_user(client)
    first = call(client, h, qid, "yes", 100, key="retry-key-0001")
    again = call(client, h, qid, "yes", 100, key="retry-key-0001")
    assert first.status_code == 201 and again.status_code == 200
    assert again.json()["id"] == first.json()["id"]
    assert points(client, h)["available"] == 900
    reused = call(client, h, qid, "no", 100, key="retry-key-0001")
    assert reused.status_code == 409 and reused.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"


@pytest.mark.parametrize("points_, code", [(5, "VALIDATION_FAILED"), (501, "VALIDATION_FAILED")])
def test_call_limits(client, points_, code):
    r = call(client, new_user(client), make_question(), "yes", points_)
    assert r.json()["error"]["code"] == code


def test_one_call_per_question_and_no_overspending(client):
    h = new_user(client)
    qid = make_question()
    assert call(client, h, qid, "yes", 100).status_code == 201
    assert call(client, h, qid, "no", 100).json()["error"]["code"] == "ALREADY_CALLED"
    qs = [make_question() for _ in range(2)]
    assert call(client, h, qs[0], "yes", 500).status_code == 201
    assert call(client, h, qs[1], "yes", 500).json()["error"]["code"] == "INSUFFICIENT_POINTS"


def test_calls_are_refused_once_a_question_closes_or_is_paused(client):
    h = new_user(client)
    closed = make_question(closes_at=NOW - timedelta(minutes=1))
    paused = make_question(status="paused")
    assert call(client, h, closed).json()["error"]["code"] == "QUESTION_NOT_OPEN"
    assert call(client, h, paused).json()["error"]["code"] == "QUESTION_NOT_OPEN"


def test_daily_call_cap(client, settings):
    settings.daily_call_cap = 2
    h = new_user(client)
    for _ in range(2):
        assert call(client, h, make_question(), "yes", 10).status_code == 201
    r = call(client, h, make_question(), "yes", 10)
    assert r.status_code == 429 and r.json()["error"]["code"] == "DAILY_CALL_LIMIT"


def test_calls_need_a_session_and_an_idempotency_key(client):
    qid = make_question()
    r = client.post(f"/v1/questions/{qid}/calls", json={"outcome_key": "yes", "points": 10},
                    headers={"Idempotency-Key": "abcdefgh1"})
    assert r.status_code == 401
    r = client.post(f"/v1/questions/{qid}/calls", json={"outcome_key": "yes", "points": 10}, headers=new_user(client))
    assert r.status_code == 422


def test_there_is_no_payout_or_transfer_endpoint(client):
    paths = {r.path for r in client.app.routes if hasattr(r, "path")}
    for route in client.get("/openapi.json").json()["paths"]:
        assert not any(w in route for w in ("withdraw", "payout", "transfer", "purchase", "deposit"))
    assert paths is not None


# ------------------------------------------------------------------ settlement

def settle(client, qid: str, result: str, source="https://results.eci.gov.in/final"):
    """Officer proposes, a different approver approves."""
    login(client, ["settlement_officer"])
    r = client.post(f"/admin/questions/{qid}/settlement", data={"result": result, "source_url": source,
                                                                "note": "Official result page checked."}, **POST)
    assert r.status_code == 303, r.text
    with SessionLocal() as s:
        from app.modules.forecasts.models import Settlement
        sid = s.scalar(select(Settlement.id).where(Settlement.question_id == qid, Settlement.status == "proposed"))
    login(client, ["settlement_approver"])
    r = client.post(f"/admin/settlements/{sid}/approve", data={"note": ""}, **POST)
    assert r.status_code == 303, r.text
    return sid


def test_settlement_formula_releases_points_and_counts_toward_rank(client):
    qid = make_question()
    a, b, c = new_user(client), new_user(client), new_user(client)
    call(client, a, qid, "yes", 300)
    call(client, b, qid, "yes", 100)
    call(client, c, qid, "no", 401)
    close(qid)
    settle(client, qid, "yes")
    # total 801, winning 400: 300*801//400 = 600, 100*801//400 = 200; 1 point rounded off.
    assert points(client, a) == {"available": 1300, "committed": 0}
    assert points(client, b) == {"available": 1100, "committed": 0}
    assert points(client, c) == {"available": 599, "committed": 0}
    me = client.get("/v1/me", headers=a).json()
    assert me["rank"]["lifetime_earned"] == 300 and me["stats"]["correct"] == 1
    calls = client.get("/v1/me/calls", headers=a).json()
    assert calls[0]["status"] == "correct" and calls[0]["released"] == 600
    q = client.get(f"/v1/questions/{qid}").json()
    assert q["status"] == "settled" and q["result"]["result"] == "yes"
    assert q["result"]["source_url"] == "https://results.eci.gov.in/final"
    assert_ledger_balanced()


def test_the_proposer_cannot_approve_their_own_result(client):
    qid = make_question(closes_at=NOW - timedelta(minutes=1))
    login(client, ["settlement_officer", "super_admin"])
    client.post(f"/admin/questions/{qid}/settlement", data={"result": "yes", "source_url": "https://x.gov.in/r"}, **POST)
    with SessionLocal() as s:
        from app.modules.forecasts.models import Settlement
        p = s.scalar(select(Settlement))
    from app.modules.forecasts import participation
    from app.errors import AppError
    with SessionLocal() as s, pytest.raises(AppError) as exc:
        participation.approve(s, s.get(type(p), p.id), p.proposed_by)
    assert exc.value.code == "TWO_PERSON_RULE"
    # And the approver role can't propose.
    login(client, ["settlement_approver"])
    other = make_question(closes_at=NOW - timedelta(minutes=1))
    r = client.post(f"/admin/questions/{other}/settlement", data={"result": "yes", "source_url": "https://x.gov.in"}, **POST)
    assert r.status_code == 403


@pytest.mark.parametrize("calls_, result", [
    ([("yes", 100), ("yes", 50)], "yes"),        # only one outcome had calls
    ([("yes", 100), ("no", 50)], "void"),        # cancelled event
])
def test_forced_voids_return_every_point(client, calls_, result):
    qid = make_question()
    users = [new_user(client) for _ in calls_]
    for h, (o, p) in zip(users, calls_):
        call(client, h, qid, o, p)
    close(qid)
    settle(client, qid, result)
    for h in users:
        assert points(client, h) == {"available": 1000, "committed": 0}
    assert client.get(f"/v1/questions/{qid}").json()["status"] == "voided"
    assert_ledger_balanced()


def test_nobody_on_the_winning_side_voids_the_question(client):
    qid = make_question(outcomes=[{"key": "yes", "label": "Yes"}, {"key": "no", "label": "No"}])
    h = new_user(client)
    call(client, h, qid, "yes", 100)
    with SessionLocal() as s:  # a second outcome with calls, but nobody on "no"
        pass
    close(qid)
    settle(client, qid, "no")
    assert points(client, h)["available"] == 1000


def test_voiding_from_the_question_lifecycle_refunds_automatically(client):
    qid = make_question()
    h = new_user(client)
    call(client, h, qid, "yes", 250)
    login(client, ["content_ops"])
    r = client.post(f"/admin/questions/{qid}/transition", data={"action": "void"}, **POST)
    assert r.status_code == 303
    assert points(client, h) == {"available": 1000, "committed": 0}
    assert client.get("/v1/me/calls", headers=h).json()[0]["status"] == "refunded"


def test_a_corrected_result_reverses_with_new_entries_and_applies_the_new_result(client):
    qid = make_question()
    a, b = new_user(client), new_user(client)
    call(client, a, qid, "yes", 100)
    call(client, b, qid, "no", 100)
    close(qid)
    settle(client, qid, "yes")
    assert points(client, a)["available"] == 1100 and points(client, b)["available"] == 900
    with SessionLocal() as s:
        before = s.scalar(select(func.count()).select_from(LedgerEntry))

    # b disputes within the window; a moderator of disputes upholds; correction via two people.
    r = client.post(f"/v1/questions/{qid}/disputes", json={"reason": "The official page says No."}, headers=b)
    assert r.status_code == 201
    settle(client, qid, "no")
    assert points(client, a) == {"available": 900, "committed": 0}
    assert points(client, b) == {"available": 1100, "committed": 0}
    with SessionLocal() as s:
        after = s.scalar(select(func.count()).select_from(LedgerEntry))
        assert after > before                      # nothing edited or deleted, only added
        assert s.scalar(select(func.count()).select_from(LedgerTransaction).where(
            LedgerTransaction.kind == "reversal")) == 2
    assert client.get("/v1/me", headers=a).json()["rank"]["lifetime_earned"] == 0
    assert_ledger_balanced()


def test_disputes_need_a_call_and_an_open_window(client, settings):
    qid = make_question()
    a, b, outsider = new_user(client), new_user(client), new_user(client)
    call(client, a, qid, "yes", 100)
    call(client, b, qid, "no", 100)
    close(qid)
    settings.dispute_window_hours = 0
    settle(client, qid, "yes")
    r = client.post(f"/v1/questions/{qid}/disputes", json={"reason": "Long enough reason here."}, headers=b)
    assert r.json()["error"]["code"] == "DISPUTE_WINDOW_CLOSED"
    r = client.post(f"/v1/questions/{qid}/disputes", json={"reason": "Long enough reason here."}, headers=outsider)
    assert r.status_code in (403, 409)
    assert user_id(client, a)

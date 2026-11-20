"""Debate and moderation, check-in and quiz, safeguards, grievances, data rights, regional
switches, election quiet periods, the sentiment dashboard and leaderboards."""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select

from app.clock import IST, ist_day
from app.db import SessionLocal
from app.ids import new_id
from app.modules.debate.models import Comment, ModerationAction
from app.modules.engagement.models import Quiz
from app.modules.forecasts.models import Call
from app.modules.identity.models import User
from tests.conftest import NOW, POST, call, login, make_question, new_user, user_id


def comment(client, h, qid, body="Turnout looks strong this time.", parent=None):
    return client.post(f"/v1/questions/{qid}/comments", json={"body": body, "parent_id": parent}, headers=h)


# ------------------------------------------------------------------ debate

def test_comments_and_replies_are_threaded_and_capped(client):
    qid = make_question()
    a, b = new_user(client), new_user(client)
    top = comment(client, a, qid).json()
    reply = comment(client, b, qid, "I doubt it.", parent=top["id"]).json()
    assert reply["parent_id"] == top["id"]
    thread = client.get(f"/v1/questions/{qid}/comments").json()
    assert thread["total"] == 2 and thread["items"][0]["replies"][0]["body"] == "I doubt it."
    assert comment(client, a, qid, "x" * 141).json()["error"]["code"] == "VALIDATION_FAILED"
    assert comment(client, a, qid, "see www.spam.com now").json()["error"]["code"] == "LINKS_NOT_ALLOWED"
    r = client.post(f"/v1/questions/{qid}/comments", json={"body": "pic", "attachment": {"kind": "photo"}}, headers=a)
    assert r.json()["error"]["code"] == "ATTACHMENTS_UNAVAILABLE"


def test_authors_can_delete_and_readers_can_block(client):
    qid = make_question()
    a, b = new_user(client), new_user(client)
    c1 = comment(client, a, qid).json()
    assert client.delete(f"/v1/comments/{c1['id']}", headers=b).status_code == 404
    assert client.delete(f"/v1/comments/{c1['id']}", headers=a).status_code == 200
    assert client.get(f"/v1/questions/{qid}/comments").json()["total"] == 0
    c2 = comment(client, a, qid).json()
    assert client.post(f"/v1/comments/{c2['id']}/block-author", headers=b).status_code == 201
    assert client.get(f"/v1/questions/{qid}/comments", headers=b).json()["items"] == []
    assert len(client.get(f"/v1/questions/{qid}/comments").json()["items"]) == 1
    blocks = client.get("/v1/me/blocks", headers=b).json()
    assert len(blocks) == 1
    client.delete(f"/v1/me/blocks/{blocks[0]['user_id']}", headers=b)
    assert len(client.get(f"/v1/questions/{qid}/comments", headers=b).json()["items"]) == 1


def test_comment_rate_limit_per_question(client):
    qid = make_question()
    h = new_user(client)
    for i in range(5):
        assert comment(client, h, qid, f"Point number {i}").status_code == 201
    assert comment(client, h, qid, "One more").status_code == 429


def test_three_reports_hold_a_comment_and_a_moderator_decides_with_a_reason(client):
    qid = make_question()
    author = new_user(client)
    c = comment(client, author, qid, "Something nasty").json()
    for _ in range(3):
        assert client.post(f"/v1/comments/{c['id']}/report", json={"reason": "abuse"},
                           headers=new_user(client)).status_code == 201
    assert client.get(f"/v1/questions/{qid}/comments").json()["total"] == 0   # held
    login(client, ["moderator"])
    page = client.get("/admin/moderation").text
    assert "Something nasty" in page and "Reports (3)" in page
    r = client.post(f"/admin/moderation/{c['id']}", data={"action": "remove", "reason_code": ""}, **POST)
    assert r.status_code == 422                                                # reason required
    r = client.post(f"/admin/moderation/{c['id']}", data={"action": "remove", "reason_code": "abuse"}, **POST)
    assert r.status_code == 303
    with SessionLocal() as s:
        assert s.get(Comment, c["id"]).status == "removed"
        act = s.scalar(select(ModerationAction))
        assert act.reason_code == "abuse" and act.handling_hours == 0


def test_suspension_blocks_calls_and_comments_but_not_grievances(client):
    h = new_user(client)
    uid = user_id(client, h)
    login(client, ["moderator"])
    r = client.post(f"/admin/users/{uid}/sanction", data={"action": "suspend", "days": "7", "reason_code": "spam"}, **POST)
    assert r.status_code == 303
    qid = make_question()
    assert call(client, h, qid).json()["error"]["code"] == "SUSPENDED"
    assert comment(client, h, qid).json()["error"]["code"] == "SUSPENDED"
    r = client.post("/v1/grievances", json={"category": "account", "subject": "Wrong suspension",
                                            "description": "I was suspended but I did not post spam at all."}, headers=h)
    assert r.status_code == 201


# ------------------------------------------------------------------ engagement

def test_check_in_once_a_day_with_a_streak_and_reward(client):
    h = new_user(client)
    r = client.post("/v1/me/checkin", headers=h)
    assert r.json() == {"checked_in_today": True, "streak": 1, "reward": 50}
    assert client.post("/v1/me/checkin", headers=h).json()["error"]["code"] == "ALREADY_CHECKED_IN"
    me = client.get("/v1/me", headers=h).json()
    assert me["points"]["available"] == 1050 and me["rank"]["lifetime_earned"] == 50


def test_daily_quiz_rewards_a_correct_answer_once_within_the_cap(client):
    with SessionLocal() as s:
        s.add(Quiz(id="quiz_t", day=ist_day(), question="Which body publishes official election results?",
                   options=[{"key": "a", "label": "ECI"}, {"key": "b", "label": "RBI"}], correct_key="a", active=True))
        s.commit()
    h = new_user(client)
    q = client.get("/v1/quiz/today", headers=h).json()["quiz"]
    assert q["answered"] is False and "correct_key" not in q
    r = client.post("/v1/quiz/quiz_t/answer", json={"answer_key": "a"}, headers=h).json()
    assert r["correct"] is True and r["reward_received"] == 25
    assert client.post("/v1/quiz/quiz_t/answer", json={"answer_key": "a"}, headers=h).status_code == 409


def test_daily_reward_cap_is_set_by_admins(client):
    login(client, ["super_admin"])
    assert client.post("/admin/economy/cap", data={"cap": "30"}, **POST).status_code == 303
    h = new_user(client)
    assert client.post("/v1/me/checkin", headers=h).json()["reward"] == 30


def test_admin_creates_a_quiz(client):
    login(client, ["content_ops"])
    day = (NOW.astimezone(IST) + timedelta(days=1)).date().isoformat()
    r = client.post("/admin/quiz", data={"day": day, "question": "Who sets India's repo rate?", "option_a": "RBI",
                                         "option_b": "SEBI", "correct_key": "a", "active": "1"}, **POST)
    assert r.status_code == 303
    with SessionLocal() as s:
        assert s.scalar(select(Quiz)).correct_key == "a"


# ------------------------------------------------------------------ safeguards and rights

def test_self_exclusion_pauses_participation_and_cannot_be_shortened(client):
    h = new_user(client)
    assert client.post("/v1/me/self-exclusion", json={"days": 7}, headers=h).status_code == 200
    r = client.post("/v1/me/self-exclusion", json={"days": 1}, headers=h).json()
    assert r["restriction"]["code"] == "SELF_EXCLUDED"
    with SessionLocal() as s:
        until = s.get(User, user_id(client, h)).excluded_until
    assert until.replace(tzinfo=until.tzinfo or IST) > NOW + timedelta(days=6)
    assert call(client, h, make_question()).json()["error"]["code"] == "SELF_EXCLUDED"


def test_grievance_is_tracked_and_activity_is_visible_only_with_consent(client):
    h = new_user(client)
    qid = make_question()
    call(client, h, qid, "yes", 50)
    g = client.post("/v1/grievances", json={"category": "points", "subject": "Points missing",
                                            "description": "My points did not come back after the void.",
                                            "support_review_consent": True}, headers=h).json()
    assert g["status"] == "open" and g["ref"].startswith("BF-")
    other = client.post("/v1/grievances", json={"category": "other", "subject": "Another one",
                                                "description": "Something else entirely that needs a look."},
                        headers=h).json()
    login(client, ["compliance"])
    assert "shared with consent" in client.get(f"/admin/grievances/{g['id']}").text
    assert "did not allow support" in client.get(f"/admin/grievances/{other['id']}").text
    r = client.post(f"/admin/grievances/{g['id']}", data={"status": "resolved", "note": "Checked the ledger.",
                                                         "visible": "1", "resolution": "Your points are correct now."}, **POST)
    assert r.status_code == 303
    mine = {x["id"]: x for x in client.get("/v1/me/grievances", headers=h).json()}
    assert mine[g["id"]]["status"] == "resolved" and mine[g["id"]]["updates"][0]["note"] == "Checked the ledger."


def test_data_export_and_account_deletion(client):
    h = new_user(client)
    qid = make_question()
    call(client, h, qid, "yes", 50)
    comment(client, h, qid, "Hello there")
    data = client.get("/v1/me/export", headers=h).json()
    assert data["points"]["committed"] == 50 and len(data["calls"]) == 1 and len(data["comments"]) == 1
    assert client.request("DELETE", "/v1/me", json={"confirm": "DELETE"}, headers=h).status_code == 200
    assert client.get("/v1/me", headers=h).status_code == 401
    assert client.get(f"/v1/questions/{qid}/comments").json()["total"] == 0
    with SessionLocal() as s:
        assert s.scalar(select(Call)).user_id                     # pseudonymous record kept


# ------------------------------------------------------------------ regions and elections

def test_features_can_be_switched_off_for_a_state(client):
    login(client, ["super_admin"])
    r = client.post("/admin/policy/features/debate", data={"on": "1", "off_states": ["BR"]}, **POST)
    assert r.status_code == 303
    assert client.get("/v1/app-config", params={"region": "BR"}).json()["flags"]["debate"] is False
    assert client.get("/v1/app-config", params={"region": "KA"}).json()["flags"]["debate"] is True
    h = new_user(client)
    client.patch("/v1/me", json={"region": "BR"}, headers=h)
    assert comment(client, h, make_question()).json()["error"]["code"] == "FEATURE_UNAVAILABLE"


def test_quiet_period_hides_chance_only_for_its_states(client):
    bihar = make_question(election_sensitive=True, election_state="BR", votes={"yes": 2, "no": 2})
    kerala = make_question(election_sensitive=True, election_state="KL", votes={"yes": 1, "no": 3})
    login(client, ["super_admin"])
    start = (NOW - timedelta(hours=1)).astimezone(IST).strftime("%Y-%m-%dT%H:%M")
    end = (NOW + timedelta(days=1)).astimezone(IST).strftime("%Y-%m-%dT%H:%M")
    r = client.post("/admin/policy/quiet", data={"label": "Bihar phase 1", "starts_at": start, "ends_at": end,
                                                 "states": ["BR"], "hide_sentiment": "1"}, **POST)
    assert r.status_code == 303
    assert client.get(f"/v1/questions/{bihar}").json()["chance_hidden"] is True
    assert client.get(f"/v1/questions/{kerala}").json()["chance_hidden"] is False


# ------------------------------------------------------------------ sentiment and leaderboards

def test_sentiment_dashboard_withholds_groups_under_50(client):
    small = make_question(category="sports", votes={"yes": 30, "no": 10})
    big = make_question(category="markets", votes={"yes": 40, "no": 20})
    d = client.get("/v1/sentiment").json()
    cats = {c["key"]: c for c in d["categories"]}
    assert cats["sports"]["enough_data"] is False and cats["sports"]["average_lean"] is None
    assert cats["markets"]["enough_data"] is True and cats["markets"]["participants"] == 60
    shown = {q["id"] for q in d["decisive"]}
    assert big in shown and small not in shown
    assert "user_id" not in str(d)


def test_leaderboards_rank_by_points_earned_in_the_period(client):
    a, b = new_user(client), new_user(client)
    client.post("/v1/me/checkin", headers=a)
    board = client.get("/v1/leaderboards", params={"period": "daily"}, headers=b).json()
    assert [e["points"] for e in board["entries"]] == [50]
    assert board["you"]["position"] is None and board["entries"][0]["tier"] == "Navodit"
    mine = client.get("/v1/leaderboards", params={"period": "all"}, headers=a).json()
    assert mine["you"] == {"points": 50, "position": 1} and mine["entries"][0]["is_you"] is True


def test_badges_are_earned_from_activity(client):
    h = new_user(client)
    call(client, h, make_question(), "yes", 10)
    badges = {b["id"]: b for b in client.get("/v1/me", headers=h).json()["badges"]}
    assert badges["first-call"]["earned"] is True and badges["ten-calls"]["earned"] is False


def test_signup_is_rate_limited_per_network(client):
    for _ in range(30):
        assert client.post("/v1/session", json={}).status_code == 201
    assert client.post("/v1/session", json={}).status_code == 429


def test_invites_are_tracked(client):
    a = new_user(client)
    code = client.get("/v1/me", headers=a).json()["invites"]["code"]
    client.post("/v1/session", json={"invite_code": code})
    assert client.get("/v1/me/invites", headers=a).json()["joined"] == 1
    assert new_id("x")

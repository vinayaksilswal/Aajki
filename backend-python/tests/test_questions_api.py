"""Public questions API: visibility, filtering, ordering, paging and the consensus figure."""
from __future__ import annotations

from datetime import timedelta

from tests.conftest import NOW, make_question


def ids(resp):
    return [q["id"] for q in resp.json()["items"]]


def test_feed_shows_only_open_published_questions(client):
    open_q = make_question()
    make_question(status="draft")
    make_question(opens_at=NOW + timedelta(hours=3))                   # scheduled
    make_question(closes_at=NOW - timedelta(minutes=1))                # closed
    make_question(status="paused")
    make_question(status="voided")
    r = client.get("/v1/questions")
    assert r.status_code == 200
    assert ids(r) == [open_q]
    assert r.json()["items"][0]["status"] == "open"


def test_closed_view_lists_questions_past_their_closing_time(client):
    closed = make_question(closes_at=NOW - timedelta(minutes=5))
    make_question()
    r = client.get("/v1/questions", params={"status": "closed"})
    assert ids(r) == [closed]
    assert r.json()["items"][0]["status"] == "closed"


def test_category_filter_and_unknown_category(client):
    sports = make_question(category="sports")
    make_question(category="markets")
    assert ids(client.get("/v1/questions", params={"category": "sports"})) == [sports]
    bad = client.get("/v1/questions", params={"category": "cricket"})
    assert bad.status_code == 400 and bad.json()["error"]["code"] == "BAD_REQUEST"


def test_search_matches_titles_and_treats_wildcards_literally(client):
    rupee = make_question(title="Will the rupee strengthen past 87 to the dollar?")
    make_question(title="Will India win the next ODI against Australia?")
    pct = make_question(title="Will repo rate cuts exceed 50% of forecasts this year?")
    assert ids(client.get("/v1/questions", params={"q": "RUPEE"})) == [rupee]
    assert ids(client.get("/v1/questions", params={"q": "50%"})) == [pct]
    assert ids(client.get("/v1/questions", params={"q": "%"})) == [pct]


def test_closing_sort_is_soonest_first(client):
    later = make_question(closes_at=NOW + timedelta(days=5))
    sooner = make_question(closes_at=NOW + timedelta(hours=2))
    assert ids(client.get("/v1/questions")) == [sooner, later]


def test_trending_sort_orders_by_participation(client):
    quiet = make_question(closes_at=NOW + timedelta(hours=2), votes={"yes": 1})
    busy = make_question(closes_at=NOW + timedelta(days=4), votes={"yes": 5, "no": 4})
    assert ids(client.get("/v1/questions", params={"sort": "trending"})) == [busy, quiet]


def test_pagination_walks_every_item_once(client):
    made = {make_question(closes_at=NOW + timedelta(hours=i + 1)) for i in range(23)}
    seen, cursor, pages = [], None, 0
    while True:
        params = {"limit": 10, **({"cursor": cursor} if cursor else {})}
        body = client.get("/v1/questions", params=params).json()
        seen += [q["id"] for q in body["items"]]
        pages += 1
        cursor = body["next_cursor"]
        if not cursor:
            break
    assert pages == 3 and len(seen) == 23 and set(seen) == made


def test_bad_cursor_and_oversized_limit_return_the_error_envelope(client):
    r = client.get("/v1/questions", params={"cursor": "not-a-cursor"})
    assert r.status_code == 400 and r.json()["error"]["code"] == "BAD_CURSOR"
    r = client.get("/v1/questions", params={"limit": 500})
    assert r.status_code == 422
    err = r.json()["error"]
    assert err["code"] == "VALIDATION_FAILED" and err["details"][0]["field"] == "limit"


def test_question_detail_visibility(client):
    open_q = make_question()
    draft = make_question(status="draft")
    scheduled = make_question(opens_at=NOW + timedelta(hours=1))
    closed = make_question(closes_at=NOW - timedelta(hours=1))
    assert client.get(f"/v1/questions/{open_q}").status_code == 200
    assert client.get(f"/v1/questions/{closed}").json()["status"] == "closed"
    for hidden in (draft, scheduled, "q_missing"):
        r = client.get(f"/v1/questions/{hidden}")
        assert r.status_code == 404 and r.json()["error"]["code"] == "NOT_FOUND"


def test_chance_is_null_until_someone_calls_then_reflects_the_split(client):
    empty = make_question()
    body = client.get(f"/v1/questions/{empty}").json()
    assert body["participants"] == 0
    assert [o["chance"] for o in body["outcomes"]] == [None, None]

    split = make_question(votes={"yes": 3, "no": 1})
    body = client.get(f"/v1/questions/{split}").json()
    assert body["participants"] == 4
    assert {o["key"]: o["chance"] for o in body["outcomes"]} == {"yes": 0.75, "no": 0.25}
    assert body["resolution"]["source_url"] == "https://results.eci.gov.in/"


def test_election_quiet_period_withholds_chance_only_on_sensitive_questions(client, settings):
    sensitive = make_question(election_sensitive=True, votes={"yes": 2, "no": 2})
    ordinary = make_question(category="sports", votes={"yes": 1, "no": 3})
    settings.election_quiet_period = True
    s_body = client.get(f"/v1/questions/{sensitive}").json()
    o_body = client.get(f"/v1/questions/{ordinary}").json()
    assert s_body["chance_hidden"] is True
    assert all(o["chance"] is None for o in s_body["outcomes"])
    assert o_body["chance_hidden"] is False and o_body["outcomes"][0]["chance"] == 0.25


def test_public_reads_are_cacheable_briefly(client):
    make_question()
    assert "max-age=10" in client.get("/v1/questions").headers["cache-control"]

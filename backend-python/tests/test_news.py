"""Ticker: ingestion, storage rules, the public feed and the scheduled job."""
from __future__ import annotations

import io
from datetime import timedelta

import pytest

from app.db import SessionLocal
from app.modules.forecasts.models import Question
from app.modules.news import ingest, service
from app.modules.news.models import NewsItem
from tests.conftest import NOW, ORIGIN, make_news, make_question


def item(n: int, **kw) -> dict:
    d = {"category": "markets", "title": f"Market headline number {n} moves the indices today",
         "source": "Example Times", "link": f"https://example.com/story-{n}", "published_at": NOW}
    d.update(kw)
    return d


def test_refresh_stores_new_headlines_once_and_prunes_old_unlinked_ones():
    linked_q = make_question()
    make_news(fetched_at=NOW - timedelta(days=40), published_at=None)                    # pruned
    keep = make_news(fetched_at=NOW - timedelta(days=40), published_at=None, question_id=linked_q)
    batch = [item(1), item(2), item(2)]                                                  # dup link
    with SessionLocal() as s:
        result = service.refresh(s, fetch=lambda: (batch, {}))
        s.commit()
    assert result == {"fetched": 3, "new": 2, "errors": {}}
    with SessionLocal() as s:
        again = service.refresh(s, fetch=lambda: (batch, {"world": "timeout"}))
        s.commit()
        assert again["new"] == 0 and again["errors"] == {"world": "timeout"}
        assert {n.id for n in s.query(NewsItem)} >= {keep}
        assert s.query(NewsItem).count() == 3


def test_ticker_is_newest_first_and_skips_hidden_and_stale(client):
    old = make_news(published_at=NOW - timedelta(hours=60))
    hidden = make_news(hidden=True)
    newer = make_news(published_at=NOW - timedelta(minutes=5))
    newest = make_news(published_at=NOW)
    body = client.get("/v1/ticker").json()
    got = [i["id"] for i in body["items"]]
    assert got == [newest, newer] and old not in got and hidden not in got
    assert body["attribution"].startswith("Headlines via Google News")


def test_ticker_links_a_headline_only_while_its_question_is_open(client):
    open_q = make_question()
    draft_q = make_question(status="draft")
    a = make_news(question_id=open_q)
    b = make_news(question_id=draft_q, published_at=NOW - timedelta(minutes=1))
    links = {i["id"]: i["question_id"] for i in client.get("/v1/ticker").json()["items"]}
    assert links == {a: open_q, b: None}


def test_drafting_from_a_headline_creates_one_private_draft(client):
    nid = make_news(title="Election Commission announces bypoll dates for three states")
    r = client.post(f"/admin/news/{nid}/draft", headers={"Origin": ORIGIN}, follow_redirects=False)
    assert r.status_code == 303
    r2 = client.post(f"/admin/news/{nid}/draft", headers={"Origin": ORIGIN}, follow_redirects=False)
    assert r2.headers["location"] == r.headers["location"]
    with SessionLocal() as s:
        (q,) = s.query(Question).all()
        assert q.status == "draft" and q.source_link == f"https://example.com/{nid}"
        assert s.get(NewsItem, nid).question_id == q.id
    assert client.get("/v1/questions").json()["items"] == []


def test_cron_requires_the_shared_secret(client, settings, monkeypatch):
    monkeypatch.setattr(ingest, "fetch_all", lambda *a, **k: ([item(9)], {}))
    assert client.get("/api/cron/news-import").status_code == 401        # no secret configured
    settings.cron_secret = "s3cret-value"
    assert client.get("/api/cron/news-import", headers={"Authorization": "Bearer nope"}).status_code == 401
    r = client.get("/api/cron/news-import", headers={"Authorization": "Bearer s3cret-value"})
    assert r.status_code == 200 and r.json()["new"] == 1


RSS = b"""<?xml version="1.0"?><rss><channel>
<item><title>RBI keeps repo rate unchanged at policy review - Example Daily</title>
<link>https://news.example/rbi</link><pubDate>Wed, 18 Nov 2026 10:00:00 GMT</pubDate>
<source url="https://example.com">Example Daily</source></item>
<item><title>Too short - X</title><link>https://news.example/short</link></item>
<item><title>Insecure link headline that is long enough to keep</title><link>http://news.example/x</link></item>
</channel></rss>"""

BOMB = b"""<?xml version="1.0"?><!DOCTYPE lolz [<!ENTITY lol "lol"><!ENTITY lol2 "&lol;&lol;&lol;">]>
<rss><channel><item><title>&lol2;</title></item></channel></rss>"""


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_feed_parsing_keeps_valid_items_and_rejects_entity_tricks(monkeypatch):
    monkeypatch.setattr(ingest.urllib.request, "urlopen", lambda req, timeout: _Resp(RSS))
    (only,) = ingest.fetch_category("markets")
    assert only["title"] == "RBI keeps repo rate unchanged at policy review"
    assert only["source"] == "Example Daily" and only["published_at"].year == 2026
    monkeypatch.setattr(ingest.urllib.request, "urlopen", lambda req, timeout: _Resp(BOMB))
    with pytest.raises(Exception):
        ingest.fetch_category("markets")
    items, errors = ingest.fetch_all()
    assert items == [] and set(errors) == set(ingest.CATEGORY_QUERIES)

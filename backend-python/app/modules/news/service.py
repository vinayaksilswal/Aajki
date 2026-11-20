"""Ticker storage, refresh and the 'draft a question from a headline' flow."""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Callable

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.errors import not_found
from app.ids import new_id
from app.modules.forecasts import service as forecasts
from app.modules.news import ingest
from app.modules.news.models import NewsItem
from app.observability import log

RETENTION = timedelta(days=30)
TICKER_LIMIT = 20


def _hash(link: str) -> str:
    return hashlib.sha256(link.encode()).hexdigest()


def refresh(s: Session, fetch: Callable | None = None) -> dict:
    """Pull the latest headlines, store new ones, prune old unlinked ones."""
    # Resolve the source at call time so a configured/substituted adapter is honoured.
    items, errors = (fetch or ingest.fetch_all)()
    now = datetime.now(timezone.utc)
    by_hash = {_hash(it["link"]): it for it in items}
    existing = set(s.scalars(select(NewsItem.link_hash)
                             .where(NewsItem.link_hash.in_(list(by_hash)))).all()) if by_hash else set()
    new = 0
    for h, it in by_hash.items():
        if h in existing:
            continue
        s.add(NewsItem(id=new_id("news"), link_hash=h, fetched_at=now, **it))
        new += 1
    s.execute(delete(NewsItem).where(NewsItem.fetched_at < now - RETENTION,
                                     NewsItem.question_id.is_(None)))
    result = {"fetched": len(items), "new": new, "errors": errors}
    log.info("news refresh", extra=result)
    return result


def ticker(s: Session, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=get_settings().ticker_window_hours)
    when = func.coalesce(NewsItem.published_at, NewsItem.fetched_at)
    rows = s.scalars(select(NewsItem).where(NewsItem.hidden.is_(False), when >= cutoff)
                     .order_by(when.desc(), NewsItem.id).limit(TICKER_LIMIT)).all()
    open_ids = forecasts.open_question_ids(s, [r.question_id for r in rows if r.question_id], now)
    return {
        "items": [{"id": r.id, "category": r.category, "title": r.title, "source": r.source,
                   "link": r.link, "published_at": forecasts.iso(r.published_at),
                   "question_id": r.question_id if r.question_id in open_ids else None}
                  for r in rows],
        "attribution": ingest.ATTRIBUTION,
        "as_of": forecasts.iso(now),
    }


def admin_recent(s: Session, limit: int = 120) -> list[NewsItem]:
    when = func.coalesce(NewsItem.published_at, NewsItem.fetched_at)
    return list(s.scalars(select(NewsItem).order_by(when.desc()).limit(limit)).all())


def draft_from_headline(s: Session, item_id: str):
    """Start a draft question from a headline. A headline is context, not a forecast: the
    admin rewrites it as a resolvable question and adds the source and rule before publishing."""
    item = s.get(NewsItem, item_id)
    if not item:
        raise not_found("Headline")
    if item.question_id:
        q = s.get(forecasts.Question, item.question_id)
        if q:
            return q
    category = item.category if item.category in forecasts.CATEGORIES else "world"
    title = item.title if len(item.title) <= 200 else item.title[:197] + "..."
    q = forecasts.create_draft(s, {
        "title": title, "category": category,
        "outcomes": forecasts.binary_outcomes("Yes", "No"),
        "description": f"Context: {item.title} ({item.source})",
        "source_headline": item.title, "source_link": item.link,
    })
    item.question_id = q.id
    return q


def set_hidden(s: Session, item_id: str, hidden: bool) -> None:
    item = s.get(NewsItem, item_id)
    if not item:
        raise not_found("Headline")
    item.hidden = hidden


def add_manual(s: Session, title: str, source: str, link: str, category: str) -> NewsItem:
    """An editor-added headline from an approved source (SOW 3.2.11)."""
    from app.errors import AppError
    from app.modules.forecasts.models import CATEGORIES
    from urllib.parse import urlparse
    title, source, link = (title or "").strip(), (source or "").strip(), (link or "").strip()
    problems = {}
    if not 10 <= len(title) <= 300:
        problems["title"] = "10 to 300 characters."
    if not 2 <= len(source) <= 200:
        problems["source"] = "Name the publisher."
    if urlparse(link).scheme != "https" or not urlparse(link).netloc:
        problems["link"] = "Use the article's https:// link."
    if category not in CATEGORIES:
        problems["category"] = "Choose a category."
    if problems:
        raise AppError(422, "VALIDATION_FAILED", "Fix the highlighted fields.", problems)
    h = _hash(link)
    if s.scalar(select(NewsItem.id).where(NewsItem.link_hash == h)):
        raise AppError(409, "CONFLICT", "That headline is already in the ticker.")
    now = datetime.now(timezone.utc)
    item = NewsItem(id=new_id("news"), category=category, title=title, source=source, link=link,
                    link_hash=h, published_at=now, fetched_at=now)
    s.add(item)
    s.flush()
    return item


def link_question(s: Session, item_id: str, question_id: str | None) -> NewsItem:
    item = s.get(NewsItem, item_id)
    if not item:
        raise not_found("Headline")
    if question_id:
        forecasts.get(s, question_id)
    item.question_id = question_id or None
    return item

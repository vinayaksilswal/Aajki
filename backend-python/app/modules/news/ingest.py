"""Headline source for the context ticker.

Staging uses the Google News RSS search feed (no key). Before public launch the spec
requires a licensed or editorial source; swap `fetch_all` for that provider's adapter.
"""
from __future__ import annotations

import urllib.parse
import urllib.request
from datetime import timezone
from email.utils import parsedate_to_datetime

from defusedxml import ElementTree as ET

SOURCE_NAME = "Google News"
ATTRIBUTION = "Headlines via Google News. Tap a headline to read it at the publisher."

# One search per spec category (Community has no news feed: it's for community questions).
CATEGORY_QUERIES = {
    "elections": "India election Election Commission",
    "markets": "Sensex Nifty RBI India economy",
    "sports": "India cricket OR football OR hockey",
    "policy": "India government policy Parliament bill",
    "world": "world news India foreign affairs",
}

_UA = "BharatForeseez-Ticker/1.0"
_MAX_BYTES = 2_000_000


def _split_title(raw: str) -> tuple[str, str | None]:
    # Google News titles read "Headline - Publisher".
    head, sep, src = raw.rpartition(" - ")
    return (head.strip(), src.strip()) if sep and head else (raw.strip(), None)


def fetch_category(category: str, limit: int = 8, recency: str = "1d", timeout: int = 15) -> list[dict]:
    query = urllib.parse.quote(f"{CATEGORY_QUERIES[category]} when:{recency}")
    url = f"https://news.google.com/rss/search?q={query}&hl=en-IN&gl=IN&ceid=IN:en"
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        root = ET.fromstring(resp.read(_MAX_BYTES))
    out, seen = [], set()
    for item in root.iter("item"):
        title, src = _split_title((item.findtext("title") or "").strip())
        link = (item.findtext("link") or "").strip()
        if len(title) < 20 or not link.startswith("https://") or title.lower() in seen:
            continue
        seen.add(title.lower())
        src_el = item.find("source")
        source = (src_el.text if src_el is not None and src_el.text else src) or SOURCE_NAME
        published = None
        if item.findtext("pubDate"):
            try:
                published = parsedate_to_datetime(item.findtext("pubDate")).astimezone(timezone.utc)
            except (TypeError, ValueError):
                published = None
        out.append({"category": category, "title": title[:400], "source": source[:200],
                    "link": link, "published_at": published})
        if len(out) >= limit:
            break
    return out


def fetch_all(limit_per_category: int = 8) -> tuple[list[dict], dict[str, str]]:
    """Returns (items, errors_by_category). One category failing doesn't stop the rest."""
    items, errors = [], {}
    for cat in CATEGORY_QUERIES:
        try:
            items.extend(fetch_category(cat, limit_per_category))
        except Exception as exc:  # network, HTTP or parse failure for this category only
            errors[cat] = f"{type(exc).__name__}: {exc}"[:200]
    return items, errors

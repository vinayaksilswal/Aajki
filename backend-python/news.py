"""Google News ingestion. Pulls recent headlines (free RSS search feed, no API key) and
turns them into 'Good news / Bad news' reaction polls, so the app tracks public mood on
real, current events. The search feed is used because the topic/top feeds are rate-limited.
"""
from __future__ import annotations

import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

# Which Google News search drives each app category.
CATEGORY_QUERIES = {
    "politics": "India politics government",
    "money": "business economy stock market",
    "tech": "technology AI startups",
    "cricket": "cricket",
    "movies": "bollywood entertainment film",
}

_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"


def _clean_title(title: str) -> tuple[str, str | None]:
    # Google News titles look like "Headline - Source"; split the source off.
    if " - " in title:
        head, _, src = title.rpartition(" - ")
        return head.strip(), src.strip()
    return title.strip(), None


def fetch_category(category: str, limit: int = 12, recency: str = "1d") -> list[dict]:
    query = CATEGORY_QUERIES.get(category, category)
    q = urllib.parse.quote(f"{query} when:{recency}")
    url = f"https://news.google.com/rss/search?q={q}&hl=en-IN&gl=IN&ceid=IN:en"
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=20) as resp:
        root = ET.fromstring(resp.read())
    out = []
    seen = set()
    for item in root.findall(".//item"):
        raw = (item.findtext("title") or "").strip()
        if not raw:
            continue
        title, source = _clean_title(raw)
        src_el = item.find("{*}source")
        source = (src_el.text if src_el is not None and src_el.text else source) or "Google News"
        key = title.lower()
        if len(title) < 20 or key in seen:
            continue
        seen.add(key)
        out.append({
            "title": title, "source": source,
            "link": (item.findtext("link") or "").strip(),
            "published": (item.findtext("pubDate") or "").strip(),
            "category": category,
        })
        if len(out) >= limit:
            break
    return out


def fetch_all(limit_per_category: int = 8) -> dict[str, list[dict]]:
    result = {}
    for cat in CATEGORY_QUERIES:
        try:
            result[cat] = fetch_category(cat, limit_per_category)
        except Exception as exc:  # one category failing shouldn't break the rest
            result[cat] = []
            print(f"news fetch failed for {cat}: {exc}")
    return result


def to_poll(item: dict) -> dict:
    """Convert a news item into args for store.admin_create_poll (a Good/Bad reaction poll)."""
    source = item.get("source") or "Google News"
    desc = f"📰 {source}"
    if item.get("link"):
        desc += f" · {item['link']}"
    return {
        "question": item["title"],
        "category": item["category"],
        "display_kind": "binary",
        "options": [
            {"key": "yes", "label": "👍 Good news", "emoji": None, "base_votes": 0},
            {"key": "no", "label": "👎 Bad news", "emoji": None, "base_votes": 0},
        ],
        "description": desc,
        "image_url": None,
        "trending": True,
        "is_prediction": False,
        "reward_coins": 5,
    }

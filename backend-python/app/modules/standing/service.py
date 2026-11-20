"""Ranks, leaderboards and badges (spec s.6, SOW 2.9, 2.10).

Rank basis: lifetime points earned (rewards plus what correct calls released beyond the
points committed). Committing points never lowers a rank. The welcome reward is a grant and
does not count, so everyone starts at the first tier.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.clock import ist_day_start, ist_week_start
from app.errors import AppError, not_found
from app.modules.engagement import service as engagement
from app.modules.forecasts import participation
from app.modules.identity import service as identity
from app.modules.ledger import service as ledger
from app.modules.policy import service as policy
from app.modules.standing.models import BADGE_RULES, Badge

PERIODS = ("daily", "weekly", "all")


def _since(period: str):
    if period == "daily":
        return ist_day_start()
    if period == "weekly":
        return ist_week_start()
    if period == "all":
        return None
    raise AppError(400, "BAD_REQUEST", "period must be daily, weekly or all.")


def rank(s: Session, lifetime: int) -> dict:
    tiers = policy.rank_tiers(s)
    current = policy.tier_for(tiers, lifetime)
    nxt = next((t for t in tiers if t["min"] > lifetime), None)
    return {"tier": current, "lifetime_earned": lifetime,
            "next": ({"name": nxt["name"], "min": nxt["min"], "points_to_go": nxt["min"] - lifetime}
                     if nxt else None),
            "tiers": tiers}


def leaderboard(s: Session, period: str, viewer_id: str | None = None, limit: int = 50) -> dict:
    since = _since(period)
    exclude = identity.blocked_ids(s)
    rows = ledger.earned_since(s, since, limit, exclude)
    profiles = identity.profiles(s, [uid for uid, _ in rows])
    lifetimes = ledger.lifetime_for(s, [uid for uid, _ in rows]) if period != "all" else dict(rows)
    tiers = policy.rank_tiers(s)
    entries = []
    for pos, (uid, pts) in enumerate(rows, start=1):
        p = profiles.get(uid, {})
        tier = policy.tier_for(tiers, lifetimes.get(uid, pts))
        entries.append({"position": pos, "display_name": p.get("display_name", "Forecaster"),
                        "avatar": p.get("avatar"), "points": pts, "tier": tier["name"],
                        "is_you": uid == viewer_id})
    you = None
    if viewer_id and viewer_id not in exclude:
        mine = ledger.earned_by(s, viewer_id, since)
        you = {"points": mine,
               "position": (ledger.users_ahead(s, mine, since, exclude) + 1) if mine > 0 else None}
    return {"period": period, "entries": entries, "you": you}


def badges_catalogue(s: Session, include_inactive: bool = False) -> list[Badge]:
    stmt = select(Badge).order_by(Badge.sort, Badge.threshold)
    if not include_inactive:
        stmt = stmt.where(Badge.active.is_(True))
    return list(s.scalars(stmt).all())


def progress(s: Session, user_id: str) -> dict[str, int]:
    acc = participation.accuracy(s, user_id)
    return {"calls": acc["calls"], "correct": acc["correct"],
            "streak": engagement.longest_streak(s, user_id),
            "lifetime": ledger.lifetime_earned(s, user_id),
            "invites": identity.invites(s, user_id)["joined"]}


def badges_for(s: Session, user_id: str, stats: dict[str, int] | None = None) -> list[dict]:
    stats = stats or progress(s, user_id)
    return [{"id": b.id, "name": b.name, "description": b.description, "emoji": b.emoji,
             "earned": stats.get(b.rule, 0) >= b.threshold, "progress": min(stats.get(b.rule, 0), b.threshold),
             "threshold": b.threshold}
            for b in badges_catalogue(s)]


def save_badge(s: Session, d: dict, badge_id: str | None = None) -> Badge:
    errors = {}
    if not 2 <= len(d.get("name") or "") <= 60:
        errors["name"] = "2 to 60 characters."
    if d.get("rule") not in BADGE_RULES:
        errors["rule"] = "Choose what the badge measures."
    if not isinstance(d.get("threshold"), int) or d["threshold"] < 1:
        errors["threshold"] = "A whole number of at least 1."
    if not (d.get("emoji") or "").strip():
        errors["emoji"] = "Pick an emoji."
    if errors:
        raise AppError(422, "VALIDATION_FAILED", "Fix the highlighted fields.", errors)
    if badge_id:
        b = s.get(Badge, badge_id)
        if not b:
            raise not_found("Badge")
    else:
        import re
        slug = re.sub(r"[^a-z0-9]+", "-", d["name"].lower()).strip("-")[:30] or "badge"
        bid, n = slug, 2
        while s.get(Badge, bid):
            bid, n = f"{slug}-{n}", n + 1
        b = Badge(id=bid)
        s.add(b)
    b.name, b.description = d["name"].strip(), (d.get("description") or "").strip()
    b.emoji, b.rule, b.threshold = d["emoji"].strip()[:8], d["rule"], d["threshold"]
    b.active, b.sort = bool(d.get("active", True)), int(d.get("sort") or 0)
    s.flush()
    return b


def badge_snapshot(b: Badge) -> dict:
    return {"name": b.name, "rule": b.rule, "threshold": b.threshold, "active": b.active}

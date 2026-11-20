"""Runtime policy set by admins: feature switches per state, the daily reward cap and the
rank thresholds (SOW 1.5, 2.5.9, 3.1.4, 3.6.3, 3.6.4).

Values live in one small table and are cached per instance for a short time, so a change
reaches every server within POLICY_TTL seconds.
"""
from __future__ import annotations

import time
from datetime import datetime

from sqlalchemy import JSON, DateTime, String, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.config import get_settings
from app.db import Base
from app.errors import AppError
from app.modules.identity.models import utcnow
from app.regions import STATES

POLICY_TTL = 30

# Phase 1 features an admin can switch off nationally or for chosen states.
FEATURES: dict[str, str] = {
    "forecasting": "Making calls on questions",
    "debate": "Comments and replies",
    "checkin": "Daily check-in",
    "quiz": "Daily quiz",
    "leaderboards": "Leaderboards",
    "sentiment_dashboard": "Sentiment dashboard",
    "invites": "Invites",
}
# Phase 2 features: always off in Phase 1 and not switchable from the panel (spec s.7).
PHASE2_FEATURES = ("prizes", "plus", "sponsored_polls", "user_created_polls", "spin_the_wheel")

DEFAULT_TIERS = [
    {"name": "Navodit", "min": 0, "emoji": "🌱", "color": "#8a8f98"},
    {"name": "Drishta", "min": 1000, "emoji": "✅", "color": "#1d9bf0"},
    {"name": "Vishleshak", "min": 2500, "emoji": "📊", "color": "#1baf7a"},
    {"name": "Top Voice", "min": 4500, "emoji": "🌟", "color": "#c98500"},
    {"name": "Hall of Famer", "min": 7000, "emoji": "🏆", "color": "#b8860b"},
    {"name": "Mahadrishta", "min": 10000, "emoji": "👑", "color": "#e8873a"},
]


class Policy(Base):
    __tablename__ = "app_policies"

    key: Mapped[str] = mapped_column(String(40), primary_key=True)
    value: Mapped[dict | list | int] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_by: Mapped[str | None] = mapped_column(String(40))


_cache: dict = {"at": 0.0, "values": None}


def _defaults() -> dict:
    return {"features": {k: {"on": True, "off_states": []} for k in FEATURES},
            "daily_reward_cap": get_settings().daily_reward_cap,
            "rank_tiers": DEFAULT_TIERS}


def values(s: Session) -> dict:
    now = time.monotonic()
    if _cache["values"] is None or now - _cache["at"] > POLICY_TTL:
        merged = _defaults()
        for row in s.scalars(select(Policy)).all():
            if row.key == "features" and isinstance(row.value, dict):
                for k, v in row.value.items():
                    if k in FEATURES and isinstance(v, dict):
                        merged["features"][k] = {"on": bool(v.get("on", True)),
                                                 "off_states": [x for x in v.get("off_states", []) if x in STATES]}
            elif row.key in merged:
                merged[row.key] = row.value
        _cache["values"], _cache["at"] = merged, now
    return _cache["values"]


def clear_cache() -> None:
    _cache["values"], _cache["at"] = None, 0.0


def flags_for(s: Session, state: str | None) -> dict[str, bool]:
    feats = values(s)["features"]
    out = {k: v["on"] and not (state and state in v["off_states"]) for k, v in feats.items()}
    out.update({k: False for k in PHASE2_FEATURES})
    return out


def require_feature(s: Session, feature: str, state: str | None) -> None:
    if not flags_for(s, state).get(feature, False):
        raise AppError(403, "FEATURE_UNAVAILABLE", "This feature isn't available in your region right now.")


def daily_reward_cap(s: Session) -> int:
    return int(values(s)["daily_reward_cap"])


def rank_tiers(s: Session) -> list[dict]:
    return values(s)["rank_tiers"]


def tier_for(tiers: list[dict], points: int) -> dict:
    current = tiers[0]
    for t in tiers:
        if points >= t["min"]:
            current = t
    return current


def _save(s: Session, key: str, value, admin_id: str) -> None:
    row = s.get(Policy, key)
    if row:
        row.value, row.updated_at, row.updated_by = value, utcnow(), admin_id
    else:
        s.add(Policy(key=key, value=value, updated_by=admin_id))
    s.flush()
    clear_cache()


def set_feature(s: Session, feature: str, on: bool, off_states: list[str], admin_id: str) -> None:
    if feature not in FEATURES:
        raise AppError(422, "VALIDATION_FAILED", "Unknown feature.")
    bad = [x for x in off_states if x not in STATES]
    if bad:
        raise AppError(422, "VALIDATION_FAILED", f"Unknown state codes: {', '.join(bad)}")
    feats = {k: dict(v) for k, v in values(s)["features"].items()}
    feats[feature] = {"on": on, "off_states": sorted(set(off_states))}
    _save(s, "features", feats, admin_id)


def set_daily_reward_cap(s: Session, cap: int, admin_id: str) -> None:
    if not 0 <= cap <= 10_000:
        raise AppError(422, "VALIDATION_FAILED", "Set a cap between 0 and 10,000 points.")
    _save(s, "daily_reward_cap", cap, admin_id)


def set_rank_thresholds(s: Session, mins: list[int], admin_id: str) -> None:
    tiers = [dict(t) for t in DEFAULT_TIERS]
    if len(mins) != len(tiers) or mins[0] != 0 or any(b <= a for a, b in zip(mins, mins[1:])):
        raise AppError(422, "VALIDATION_FAILED", "Thresholds must start at 0 and rise for each rank.")
    for t, m in zip(tiers, mins):
        t["min"] = int(m)
    _save(s, "rank_tiers", tiers, admin_id)

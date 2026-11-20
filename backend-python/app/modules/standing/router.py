"""Leaderboards, rank tiers and the badge catalogue."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Response

from app.db import SessionLocal
from app.modules.identity.deps import optional_user
from app.modules.identity.models import User
from app.modules.policy import service as policy
from app.modules.standing import service

router = APIRouter(prefix="/v1", tags=["standing"])


@router.get("/leaderboards")
def leaderboard(response: Response, period: Literal["daily", "weekly", "all"] = "weekly",
                viewer: User | None = Depends(optional_user)):
    with SessionLocal() as s:
        policy.require_feature(s, "leaderboards", viewer.region if viewer else None)
        out = service.leaderboard(s, period, viewer.id if viewer else None)
    response.headers["Cache-Control"] = "no-store"
    return out


@router.get("/badges")
def badges():
    with SessionLocal() as s:
        return [{"id": b.id, "name": b.name, "description": b.description, "emoji": b.emoji,
                 "rule": b.rule, "threshold": b.threshold} for b in service.badges_catalogue(s)]

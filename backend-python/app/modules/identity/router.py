"""App session, profile, safeguards and data rights.

POST /v1/session issues a pseudonymous device account until phone sign-in (M2) ships.
"""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from app.db import SessionLocal, session_scope
from app.modules.compliance import service as compliance
from app.modules.debate import service as debate
from app.modules.engagement import service as engagement
from app.modules.forecasts import participation
from app.modules.identity import service
from app.modules.identity.deps import current_user
from app.modules.identity.models import User
from app.modules.ledger import service as ledger
from app.modules.policy import service as policy
from app.modules.standing import service as standing
from app.ratelimit import client_ip, hit

router = APIRouter(prefix="/v1", tags=["account"])


class SessionIn(BaseModel):
    invite_code: str | None = Field(None, max_length=16)


class ProfileIn(BaseModel):
    display_name: str | None = Field(None, max_length=40)
    region: str | None = Field(None, max_length=4)
    clear_region: bool = False
    avatar: str | None = Field(None, max_length=24)


class ExclusionIn(BaseModel):
    days: Literal[1, 7, 30, 90]


class DeleteIn(BaseModel):
    confirm: Literal["DELETE"]


@router.post("/session", status_code=201)
def start_session(request: Request, body: SessionIn | None = None):
    """A new device account with its welcome reward. Limited per network address so accounts
    can't be mass-created to farm rewards or skew the sentiment index (SOW 4.1.4). The limits
    are generous because Indian mobile carriers put many people behind one address (CGNAT);
    device integrity checks in the Android shell are the stronger control."""
    ip = client_ip(request)
    hit("signup-h", ip, 30, 3600, "Too many new accounts from this network. Try again later.")
    hit("signup-d", ip, 200, 86400, "Too many new accounts from this network today.")
    with session_scope() as s:
        user, token = service.start_device_session(s, body.invite_code if body else None)
        return {"token": token, "user_id": user.id}


def _me(s, user: User) -> dict:
    stats = standing.progress(s, user.id)
    acc = participation.accuracy(s, user.id)
    badges = standing.badges_for(s, user.id, stats)
    return {
        "id": user.id, "display_name": user.display_name, "avatar": user.avatar,
        "region": user.region, "kind": user.kind, "created_at": user.created_at.isoformat(),
        "points": ledger.user_balances(s, user.id),
        "rank": standing.rank(s, stats["lifetime"]),
        "stats": {**acc, "longest_streak": stats["streak"]},
        "badges": badges,
        "checkin": engagement.checkin_status(s, user.id),
        "calls_today": participation.calls_today(s, user.id),
        "invites": service.invites(s, user.id),
        "restriction": service.restriction(user),
        "flags": policy.flags_for(s, user.region),
    }


@router.get("/me")
def me(user: User = Depends(current_user)):
    with SessionLocal() as s:
        return _me(s, s.get(User, user.id))


@router.patch("/me")
def update_me(body: ProfileIn, user: User = Depends(current_user)):
    with session_scope() as s:
        if body.display_name is not None:
            hit("rename", user.id, 5, 86400, "You can change your name a few times a day.")
            service.set_display_name(s, user.id, body.display_name)
        service.set_profile(s, user.id, region=body.region, avatar=body.avatar,
                            clear_region=body.clear_region)
        s.flush()
        return _me(s, s.get(User, user.id))


@router.post("/me/self-exclusion")
def self_exclusion(body: ExclusionIn, user: User = Depends(current_user)):
    with session_scope() as s:
        u = service.self_exclude(s, user.id, body.days)
        return {"restriction": service.restriction(u)}


@router.get("/me/export")
def export(user: User = Depends(current_user)):
    """DPDP data-access request: a copy of the personal data held about this account."""
    hit("export", user.id, 5, 3600, "Try again in a little while.")
    with SessionLocal() as s:
        u = s.get(User, user.id)
        txns, cursor = [], None
        while True:
            page = ledger.history(s, user.id, cursor, 100)
            txns.extend(page["items"])
            cursor = page["next_cursor"]
            if not cursor or len(txns) >= 10_000:
                break
        return {"account": service.export(u), "points": ledger.user_balances(s, user.id),
                "ledger": txns, "calls": participation.my_calls(s, user.id, None, limit=10_000),
                "comments": debate.user_comments(s, user.id),
                "grievances": compliance.my_grievances(s, user.id),
                "disputes": participation.my_disputes(s, user.id)}


@router.delete("/me")
def delete_me(body: DeleteIn, user: User = Depends(current_user)):
    """DPDP erasure. The account is closed and its personal details removed."""
    with session_scope() as s:
        debate.erase_user(s, user.id)
        service.delete_account(s, user.id)
    return {"deleted": True}


@router.get("/me/blocks")
def my_blocks(user: User = Depends(current_user)):
    with SessionLocal() as s:
        ids = sorted(debate.blocked_by(s, user.id))
        profiles = service.profiles(s, ids)
        return [{"user_id": i, "display_name": profiles.get(i, {}).get("display_name", "Forecaster")}
                for i in ids]


@router.delete("/me/blocks/{user_id}")
def unblock(user_id: str, user: User = Depends(current_user)):
    with session_scope() as s:
        debate.unblock(s, user.id, user_id[:40])
    return {"ok": True}


@router.get("/me/invites")
def my_invites(user: User = Depends(current_user)):
    with SessionLocal() as s:
        policy.require_feature(s, "invites", user.region)
        return service.invites(s, user.id)

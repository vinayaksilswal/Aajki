"""The user's own points ledger. Read only: points move through calls and rewards, and the
ledger has no payout, withdrawal or transfer endpoint."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.db import SessionLocal
from app.modules.identity.deps import current_user
from app.modules.identity.models import User
from app.modules.ledger import service

router = APIRouter(prefix="/v1/me", tags=["ledger"])


@router.get("/ledger")
def my_ledger(user: User = Depends(current_user), cursor: str | None = Query(None, max_length=200),
              limit: int = Query(30, ge=1, le=100)):
    with SessionLocal() as s:
        return {**service.history(s, user.id, cursor, limit), **service.user_balances(s, user.id)}

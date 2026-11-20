"""Daily check-in and daily quiz."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.db import SessionLocal, session_scope
from app.modules.engagement import service
from app.modules.identity import service as identity
from app.modules.identity.deps import current_user, optional_user
from app.modules.identity.models import User
from app.modules.policy import service as policy

router = APIRouter(prefix="/v1", tags=["engagement"])


class AnswerIn(BaseModel):
    answer_key: str = Field(max_length=8)


@router.post("/me/checkin")
def check_in(user: User = Depends(current_user)):
    identity.ensure_can_participate(user)
    with session_scope() as s:
        policy.require_feature(s, "checkin", user.region)
        return service.check_in(s, user.id)


@router.get("/quiz/today")
def quiz_today(user: User | None = Depends(optional_user)):
    with SessionLocal() as s:
        return {"quiz": service.today_quiz(s, user.id if user else None)}


@router.post("/quiz/{quiz_id}/answer")
def answer(quiz_id: str, body: AnswerIn, user: User = Depends(current_user)):
    identity.ensure_can_participate(user)
    with session_scope() as s:
        policy.require_feature(s, "quiz", user.region)
        return service.answer_quiz(s, user.id, quiz_id[:40], body.answer_key)

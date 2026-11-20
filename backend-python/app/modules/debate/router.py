"""Debate API: comments and replies, delete, report and block."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, Field

from app.db import SessionLocal, session_scope
from app.errors import AppError, not_found
from app.modules.debate import service
from app.modules.forecasts import service as forecasts
from app.modules.forecasts.models import Question
from app.modules.identity import service as identity
from app.modules.identity.deps import current_user, optional_user
from app.modules.identity.models import User
from app.modules.policy import service as policy
from app.ratelimit import hit

router = APIRouter(prefix="/v1", tags=["debate"])


class CommentIn(BaseModel):
    body: str = Field(max_length=400)
    parent_id: int | None = None
    # Attachments need automated screening and storage, neither configured yet (see models).
    attachment: dict | None = None


class ReportIn(BaseModel):
    reason: str = Field(max_length=16)
    note: str | None = Field(None, max_length=280)


def _public_question(s, question_id: str):
    q = s.get(Question, question_id)
    if not q or not forecasts.is_public(q):
        raise not_found("Question")
    return q


@router.get("/questions/{question_id}/comments")
def comments(question_id: str, response: Response, viewer: User | None = Depends(optional_user),
             before: int | None = Query(None, ge=1), limit: int = Query(20, ge=1, le=50)):
    with SessionLocal() as s:
        _public_question(s, question_id[:40])
        out = service.thread(s, question_id[:40], viewer.id if viewer else None, identity.profiles,
                             limit=limit, before_id=before)
    response.headers["Cache-Control"] = "no-store"
    return out


@router.post("/questions/{question_id}/comments", status_code=201)
def post_comment(question_id: str, body: CommentIn, user: User = Depends(current_user)):
    if body.attachment:
        raise AppError(422, "ATTACHMENTS_UNAVAILABLE",
                       "Photos, videos and voice notes open once automated screening is live.")
    identity.ensure_can_participate(user)
    hit("comment-user", user.id, 20, 3600, "You've posted a lot this hour. Take a short break.")
    hit("comment-q", f"{user.id}:{question_id}", 5, 3600,
        "You've posted a lot on this question this hour.")
    with session_scope() as s:
        policy.require_feature(s, "debate", user.region)
        _public_question(s, question_id[:40])
        c = service.post(s, user.id, user.display_name, question_id[:40], body.body, body.parent_id)
        profiles = identity.profiles(s, [user.id])
        return service._out(c, user.id, profiles)


@router.delete("/comments/{comment_id}")
def delete_comment(comment_id: int, user: User = Depends(current_user)):
    with session_scope() as s:
        service.delete_own(s, user.id, comment_id)
    return {"deleted": True}


@router.post("/comments/{comment_id}/report", status_code=201)
def report_comment(comment_id: int, body: ReportIn, user: User = Depends(current_user)):
    hit("report", user.id, 30, 3600, "You've sent a lot of reports this hour.")
    with session_scope() as s:
        service.report(s, user.id, comment_id, body.reason, body.note)
    return {"reported": True}


@router.post("/comments/{comment_id}/block-author", status_code=201)
def block_author(comment_id: int, user: User = Depends(current_user)):
    with session_scope() as s:
        author = service.author_of(s, comment_id)
        if not author:
            raise not_found("Comment")
        service.block(s, user.id, author)
    return {"blocked": True}

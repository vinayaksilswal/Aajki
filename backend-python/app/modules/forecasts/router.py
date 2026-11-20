"""Public forecasts API: the question feed, calls, "My calls" and result disputes."""
from __future__ import annotations

import re
from typing import Literal

from fastapi import APIRouter, Depends, Header, Query, Response

from app.db import SessionLocal, session_scope
from app.errors import AppError
from app.modules.compliance import service as compliance
from app.modules.forecasts import participation, service
from app.modules.forecasts.schemas import CallIn, CallOut, DisputeIn, QuestionOut, QuestionPage
from app.modules.identity import service as identity
from app.modules.identity.deps import current_user
from app.modules.identity.models import User
from app.modules.policy import service as policy
from app.ratelimit import hit

router = APIRouter(prefix="/v1", tags=["forecasts"])

# Separate directives per cache layer. Browsers must revalidate every time: the app schedules
# its own refreshes, and a browser serving stale data would hide a just-published question
# (and mask an outage). Only the CDN (CDN-Cache-Control, RFC 9213) absorbs read bursts.
_BROWSER_CACHE = "no-cache"
_CDN_CACHE = "public, s-maxage=15, stale-while-revalidate=30"
_IDEMPOTENCY_KEY = re.compile(r"^[A-Za-z0-9_\-]{8,80}$")


def _cache(response: Response) -> None:
    response.headers["Cache-Control"] = _BROWSER_CACHE
    response.headers["CDN-Cache-Control"] = _CDN_CACHE


@router.get("/questions", response_model=QuestionPage)
def list_questions(
    response: Response,
    status: Literal["open", "closed", "settled"] = "open",
    category: str | None = Query(None, max_length=20),
    q: str | None = Query(None, max_length=80, description="Search in question titles"),
    sort: Literal["closing", "trending"] = "closing",
    cursor: str | None = Query(None, max_length=200),
    limit: int = Query(20, ge=1, le=service.MAX_PAGE),
):
    with SessionLocal() as s:
        page = service.list_public(s, status=status, category=category, search=q, sort=sort,
                                   cursor=cursor, limit=limit, quiet=compliance.quiet_states(s))
        if status != "open":
            results = participation.results_for(s, [i["id"] for i in page["items"]])
            for item in page["items"]:
                item["result"] = results.get(item["id"])
    _cache(response)
    return page


@router.get("/questions/{question_id}", response_model=QuestionOut)
def get_question(question_id: str, response: Response):
    with SessionLocal() as s:
        out = service.get_public(s, question_id[:40], quiet=compliance.quiet_states(s))
        out["result"] = participation.public_result(s, out["id"])
    _cache(response)
    return out


@router.post("/questions/{question_id}/calls", response_model=CallOut, status_code=201)
def make_call(question_id: str, body: CallIn, response: Response,
              user: User = Depends(current_user),
              idempotency_key: str = Header(..., alias="Idempotency-Key")):
    """Commit points to an outcome. The Idempotency-Key header is required: a retried request
    with the same key returns the original call and never commits points twice."""
    if not _IDEMPOTENCY_KEY.match(idempotency_key):
        raise AppError(400, "BAD_IDEMPOTENCY_KEY", "Idempotency-Key must be 8 to 80 letters, digits, - or _.")
    identity.ensure_can_participate(user)
    hit("call", user.id, 30, 60, "Too many calls at once. Wait a minute and try again.")
    with session_scope() as s:
        policy.require_feature(s, "forecasting", user.region)
        call, created = participation.place_call(s, user.id, question_id[:40], body.outcome_key,
                                                 body.points, idempotency_key)
    if not created:
        response.status_code = 200
    return call


@router.get("/me/calls", response_model=list[CallOut])
def my_calls(user: User = Depends(current_user),
             status: Literal["all", "active", "settled"] = "all"):
    with SessionLocal() as s:
        return participation.my_calls(s, user.id, None if status == "all" else status)


@router.get("/questions/{question_id}/my-call", response_model=CallOut | None)
def my_call(question_id: str, user: User = Depends(current_user)):
    with SessionLocal() as s:
        return participation.my_call_on(s, user.id, question_id[:40])


@router.post("/questions/{question_id}/disputes", status_code=201)
def dispute(question_id: str, body: DisputeIn, user: User = Depends(current_user)):
    hit("dispute", user.id, 5, 3600, "Too many disputes. Try again later.")
    with session_scope() as s:
        d = participation.raise_dispute(s, user.id, question_id[:40], body.reason, body.evidence_url)
        return {"id": d.id, "status": d.status}


@router.get("/me/disputes")
def my_disputes(user: User = Depends(current_user)):
    with SessionLocal() as s:
        return participation.my_disputes(s, user.id)

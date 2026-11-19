"""Public forecasts API."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Query, Response

from app.db import SessionLocal
from app.modules.forecasts import service
from app.modules.forecasts.schemas import QuestionOut, QuestionPage

router = APIRouter(prefix="/v1", tags=["forecasts"])

# Separate directives per cache layer. Browsers must revalidate every time: the app schedules
# its own refreshes, and a browser serving stale data would hide a just-published question
# (and mask an outage). Only the CDN (CDN-Cache-Control, RFC 9213) absorbs read bursts.
_BROWSER_CACHE = "no-cache"
_CDN_CACHE = "public, s-maxage=15, stale-while-revalidate=30"


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
                                   cursor=cursor, limit=limit)
    _cache(response)
    return page


@router.get("/questions/{question_id}", response_model=QuestionOut)
def get_question(question_id: str, response: Response):
    with SessionLocal() as s:
        out = service.get_public(s, question_id[:40])
    _cache(response)
    return out

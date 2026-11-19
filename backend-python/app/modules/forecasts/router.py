"""Public forecasts API."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Query, Response

from app.db import SessionLocal
from app.modules.forecasts import service
from app.modules.forecasts.schemas import QuestionOut, QuestionPage

router = APIRouter(prefix="/v1", tags=["forecasts"])

# Short shared cache: the CDN absorbs read bursts; consensus is at most a few seconds stale.
_CACHE = "public, max-age=10, s-maxage=15, stale-while-revalidate=30"


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
    response.headers["Cache-Control"] = _CACHE
    return page


@router.get("/questions/{question_id}", response_model=QuestionOut)
def get_question(question_id: str, response: Response):
    with SessionLocal() as s:
        out = service.get_public(s, question_id[:40])
    response.headers["Cache-Control"] = _CACHE
    return out

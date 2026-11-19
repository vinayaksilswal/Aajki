"""Public ticker API."""
from __future__ import annotations

from fastapi import APIRouter, Response
from pydantic import BaseModel

from app.db import SessionLocal
from app.modules.news import service

router = APIRouter(prefix="/v1", tags=["news"])


class TickerItem(BaseModel):
    id: str
    category: str
    title: str
    source: str
    link: str
    published_at: str | None
    # Set when an open question was drafted from this headline.
    question_id: str | None


class Ticker(BaseModel):
    items: list[TickerItem]
    attribution: str
    as_of: str


@router.get("/ticker", response_model=Ticker)
def get_ticker(response: Response):
    with SessionLocal() as s:
        out = service.ticker(s)
    response.headers["Cache-Control"] = "public, max-age=60, s-maxage=120, stale-while-revalidate=300"
    return out

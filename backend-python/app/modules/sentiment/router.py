"""Public national sentiment dashboard (aggregates only, minimum group of 50)."""
from __future__ import annotations

from fastapi import APIRouter, Response

from app.db import SessionLocal
from app.modules.compliance import service as compliance
from app.modules.sentiment import public

router = APIRouter(prefix="/v1", tags=["sentiment"])


@router.get("/sentiment")
def sentiment(response: Response):
    with SessionLocal() as s:
        out = public.dashboard(s, compliance.quiet_states(s, sentiment=True))
    response.headers["Cache-Control"] = "no-cache"
    response.headers["CDN-Cache-Control"] = "public, s-maxage=60, stale-while-revalidate=120"
    return out

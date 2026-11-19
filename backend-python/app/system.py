"""Health, app configuration and scheduled jobs."""
from __future__ import annotations

import hmac

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import text

from app.config import get_settings
from app.db import SessionLocal, session_scope
from app.errors import body
from app.modules.forecasts.models import CATEGORIES
from app.modules.news import service as news
from app.observability import log

router = APIRouter()

# Phase 1 ships status-only rewards. Everything below stays off until counsel and the
# client approve the Phase 2 scope (spec s.2, s.7).
PHASE1_FLAGS = {"prizes": False, "plus": False, "sponsored_polls": False,
                "user_created_polls": False, "spin_the_wheel": False}


@router.get("/healthz", include_in_schema=False)
def healthz():
    try:
        with SessionLocal() as s:
            s.execute(text("SELECT 1"))
        return {"status": "ok"}
    except Exception:
        log.exception("health check: database unreachable")
        return JSONResponse({"status": "degraded", "database": "unreachable"}, status_code=503)


class GrievanceOfficer(BaseModel):
    name: str | None
    email: str | None
    phone: str | None
    address: str | None


class AppConfig(BaseModel):
    min_supported_build: int
    latest_build: int
    flags: dict[str, bool]
    categories: list[dict[str, str]]
    grievance_officer: GrievanceOfficer
    legal: dict[str, str | None]


@router.get("/v1/app-config", response_model=AppConfig, tags=["system"])
def app_config(response: Response):
    st = get_settings()
    response.headers["Cache-Control"] = "public, max-age=300, s-maxage=300"
    return {
        "min_supported_build": st.min_supported_build,
        "latest_build": st.latest_build,
        "flags": PHASE1_FLAGS,
        "categories": [{"key": k, "label": v} for k, v in CATEGORIES.items()],
        "grievance_officer": {"name": st.grievance_officer_name or None,
                              "email": st.grievance_officer_email or None,
                              "phone": st.grievance_officer_phone or None,
                              "address": st.grievance_officer_address or None},
        "legal": {"privacy_notice_url": st.privacy_notice_url or None,
                  "terms_url": st.terms_url or None},
    }


@router.get("/api/cron/news-import", include_in_schema=False)
def cron_news_import(request: Request):
    """Scheduled headline refresh (Vercel Cron sends `Authorization: Bearer $CRON_SECRET`)."""
    secret = get_settings().cron_secret
    sent = request.headers.get("authorization", "")
    if not secret or not hmac.compare_digest(sent.encode(), f"Bearer {secret}".encode()):
        return JSONResponse(body("UNAUTHORIZED", "Missing or wrong cron secret."), status_code=401)
    with session_scope() as s:
        result = news.refresh(s)
    return {"ok": True, **result}

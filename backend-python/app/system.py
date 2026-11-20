"""Health, app configuration and scheduled jobs."""
from __future__ import annotations

import hmac

from fastapi import APIRouter, Query, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import text

from app.config import get_settings
from app.db import SessionLocal, session_scope
from app.errors import body
from app.modules.compliance import service as compliance
from app.modules.debate.service import REPORT_REASONS
from app.modules.forecasts.models import CATEGORIES
from app.modules.identity.service import AVATARS, SELF_EXCLUSION_DAYS
from app.modules.news import service as news
from app.modules.policy import service as policy
from app.observability import log
from app.regions import STATES

router = APIRouter()

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
    # Phase 1 feature switches for the region asked for (Phase 2 features are always off).
    flags: dict[str, bool]
    categories: list[dict[str, str]]
    states: list[dict[str, str]]
    rules: dict
    rank_tiers: list[dict]
    report_reasons: list[dict[str, str]]
    grievance_categories: list[dict[str, str]]
    avatars: list[str]
    election_quiet_period: bool
    grievance_officer: GrievanceOfficer
    legal: dict[str, str | None]


@router.get("/v1/app-config", response_model=AppConfig, tags=["system"])
def app_config(response: Response, region: str | None = Query(None, max_length=4)):
    st = get_settings()
    response.headers["Cache-Control"] = "no-cache"
    response.headers["CDN-Cache-Control"] = "public, s-maxage=60, stale-while-revalidate=120"
    with SessionLocal() as s:
        flags = policy.flags_for(s, region if region in STATES else None)
        tiers = policy.rank_tiers(s)
        cap = policy.daily_reward_cap(s)
        quiet = bool(compliance.quiet_states(s))
    return {
        "min_supported_build": st.min_supported_build,
        "latest_build": st.latest_build,
        "flags": flags,
        "categories": [{"key": k, "label": v} for k, v in CATEGORIES.items()],
        "states": [{"code": k, "name": v} for k, v in sorted(STATES.items(), key=lambda kv: kv[1])],
        "rules": {"daily_call_cap": st.daily_call_cap, "call_min_points": st.call_min_points,
                  "call_max_points": st.call_max_points, "signup_reward": st.signup_reward,
                  "checkin_reward": st.checkin_reward, "quiz_reward": st.quiz_reward,
                  "daily_reward_cap": cap, "dispute_window_hours": st.dispute_window_hours,
                  "session_reminder_minutes": st.session_reminder_minutes,
                  "self_exclusion_days": list(SELF_EXCLUSION_DAYS), "comment_max_length": 140,
                  "min_group": 50},
        "rank_tiers": tiers,
        "report_reasons": [{"key": k, "label": v} for k, v in REPORT_REASONS.items()],
        "grievance_categories": [{"key": k, "label": v} for k, v in compliance.GRIEVANCE_CATEGORIES.items()],
        "avatars": list(AVATARS),
        "election_quiet_period": quiet,
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

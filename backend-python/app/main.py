"""Bharat Foreseez API: one deployable backend with internal modules (spec s.5)."""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app import errors
from app.config import get_settings
from app.modules.compliance.router import router as compliance_router
from app.modules.debate.router import router as debate_router
from app.modules.engagement.router import router as engagement_router
from app.modules.forecasts.router import router as forecasts_router
from app.modules.governance.admin_router import router as admin_router
from app.modules.governance.ops import record_error
from app.modules.identity.router import router as identity_router
from app.modules.ledger.router import router as ledger_router
from app.modules.news.router import router as news_router
from app.modules.sentiment.router import router as sentiment_router
from app.modules.standing.router import router as standing_router
from app.observability import HEADER, CorrelationMiddleware, configure_logging
from app.system import router as system_router

ADMIN_CSP = ("default-src 'none'; style-src 'unsafe-inline'; img-src https: data:; "
             "script-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'")


def _init_sentry(dsn: str, env: str) -> None:
    """Error reporting. No request bodies, cookies, headers or user identifiers are sent."""
    try:
        import sentry_sdk
    except ImportError:  # pragma: no cover
        return

    def scrub(event, _hint):
        req = event.get("request") or {}
        for key in ("cookies", "data", "headers", "query_string"):
            req.pop(key, None)
        event.pop("user", None)
        return event

    sentry_sdk.init(dsn=dsn, environment=env, send_default_pii=False, traces_sample_rate=0.0,
                    before_send=scrub)


def create_app() -> FastAPI:
    settings = get_settings()
    settings.check()
    configure_logging()
    if settings.sentry_dsn:
        _init_sentry(settings.sentry_dsn, settings.app_env)

    app = FastAPI(title="Bharat Foreseez API", version="0.5.0",
                  docs_url="/docs" if settings.is_dev else None,
                  redoc_url=None, openapi_url="/openapi.json" if settings.is_dev else None)

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        if response.status_code >= 500:
            record_error("5xx")
        h = response.headers
        h.setdefault("X-Content-Type-Options", "nosniff")
        h.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        if request.url.path.startswith("/admin"):
            h["Cache-Control"] = "no-store"
            h["X-Frame-Options"] = "DENY"
            h["Content-Security-Policy"] = ADMIN_CSP
        elif "Cache-Control" not in h:
            h["Cache-Control"] = "no-store"
        if not settings.is_dev:
            h.setdefault("Strict-Transport-Security", "max-age=63072000; includeSubDomains")
        return response

    app.add_middleware(CorrelationMiddleware)
    # Added last so it is outermost: error responses carry CORS headers too.
    app.add_middleware(CORSMiddleware, allow_origins=settings.origins, allow_credentials=False,
                       allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
                       allow_headers=["Content-Type", "Authorization", HEADER, "Idempotency-Key"],
                       expose_headers=[HEADER], max_age=600)

    errors.install(app)
    for r in (system_router, forecasts_router, news_router, identity_router, ledger_router,
              debate_router, engagement_router, standing_router, compliance_router, sentiment_router,
              admin_router):
        app.include_router(r)
    return app

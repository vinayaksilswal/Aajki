"""Bharat Foreseez API: one deployable backend with internal modules (spec s.5)."""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app import errors
from app.config import get_settings
from app.modules.forecasts.router import router as forecasts_router
from app.modules.governance.admin_router import router as admin_router
from app.modules.news.router import router as news_router
from app.observability import HEADER, CorrelationMiddleware, configure_logging
from app.system import router as system_router

ADMIN_CSP = ("default-src 'none'; style-src 'unsafe-inline'; img-src https: data:; "
             "script-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'")


def create_app() -> FastAPI:
    settings = get_settings()
    settings.check()
    configure_logging()

    app = FastAPI(title="Bharat Foreseez API", version="0.4.0",
                  docs_url="/docs" if settings.is_dev else None,
                  redoc_url=None, openapi_url="/openapi.json" if settings.is_dev else None)

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
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
                       allow_methods=["GET", "POST", "OPTIONS"],
                       allow_headers=["Content-Type", "Authorization", HEADER, "Idempotency-Key"],
                       expose_headers=[HEADER], max_age=600)

    errors.install(app)
    app.include_router(system_router)
    app.include_router(forecasts_router)
    app.include_router(news_router)
    app.include_router(admin_router)
    return app

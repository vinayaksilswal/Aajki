"""One error envelope for every API failure:

    {"error": {"code": "NOT_FOUND", "message": "...", "correlation_id": "...", "details": ...}}

Expected failures raise AppError; framework errors are translated here. Unexpected
exceptions are logged with their correlation ID and return a generic 500.
"""
from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.observability import correlation_id, log

_STATUS_CODES = {400: "BAD_REQUEST", 401: "UNAUTHORIZED", 403: "FORBIDDEN", 404: "NOT_FOUND",
                 405: "METHOD_NOT_ALLOWED", 409: "CONFLICT", 422: "VALIDATION_FAILED",
                 429: "RATE_LIMITED", 503: "UNAVAILABLE"}


class AppError(Exception):
    def __init__(self, status: int, code: str, message: str, details: Any = None):
        super().__init__(message)
        self.status, self.code, self.message, self.details = status, code, message, details


def not_found(what: str = "Resource") -> AppError:
    return AppError(404, "NOT_FOUND", f"{what} not found.")


def body(code: str, message: str, details: Any = None) -> dict:
    err = {"code": code, "message": message, "correlation_id": correlation_id.get()}
    if details is not None:
        err["details"] = details
    return {"error": err}


def install(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError):
        return JSONResponse(body(exc.code, exc.message, exc.details), status_code=exc.status)

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException):
        code = _STATUS_CODES.get(exc.status_code, "ERROR")
        msg = exc.detail if isinstance(exc.detail, str) else code.replace("_", " ").capitalize()
        return JSONResponse(body(code, msg), status_code=exc.status_code,
                            headers=getattr(exc, "headers", None))

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError):
        details = [{"field": ".".join(str(p) for p in e["loc"][1:]), "issue": e["msg"]}
                   for e in exc.errors()]
        return JSONResponse(body("VALIDATION_FAILED", "Some fields are invalid.", details),
                            status_code=422)

    @app.exception_handler(Exception)
    async def _unexpected(_: Request, exc: Exception):
        log.exception("unhandled error")
        from app.modules.governance.ops import record_error  # lazy: avoids an import cycle
        record_error("5xx")
        return JSONResponse(body("INTERNAL", "Something went wrong. Please try again."),
                            status_code=500)

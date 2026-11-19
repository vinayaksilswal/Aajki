"""Correlation IDs and structured JSON logs.

Every request carries one correlation ID from the app through the backend: the client's
`X-Correlation-ID` is kept when well-formed, otherwise one is generated. It is echoed in
the response header, attached to every log line and included in error bodies, so a user's
error report links straight to the server logs.
"""
from __future__ import annotations

import json
import logging
import re
import time
import uuid
from contextvars import ContextVar
from datetime import datetime, timezone

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

HEADER = "X-Correlation-ID"
_VALID = re.compile(r"^[A-Za-z0-9._-]{8,64}$")
correlation_id: ContextVar[str] = ContextVar("correlation_id", default="-")

log = logging.getLogger("bf")


class JsonFormatter(logging.Formatter):
    _SKIP = set(vars(logging.makeLogRecord({}))) | {"message", "asctime"}

    def format(self, record: logging.LogRecord) -> str:
        doc = {"ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
               "level": record.levelname.lower(), "msg": record.getMessage(),
               "cid": correlation_id.get()}
        doc.update({k: v for k, v in vars(record).items() if k not in self._SKIP})
        if record.exc_info:
            doc["exc"] = self.formatException(record.exc_info)
        return json.dumps(doc, default=str)


def configure_logging(level: int = logging.INFO) -> None:
    if any(isinstance(h.formatter, JsonFormatter) for h in log.handlers):
        return
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    log.addHandler(handler)
    log.setLevel(level)
    log.propagate = False


class CorrelationMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        incoming = request.headers.get(HEADER, "")
        cid = incoming if _VALID.match(incoming) else uuid.uuid4().hex
        token = correlation_id.set(cid)
        start = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            correlation_id.reset(token)
        response.headers[HEADER] = cid
        # Log the route template, never raw query strings (search terms can be personal).
        route = request.scope.get("route")
        log.info("request", extra={"cid": cid, "method": request.method,
                                   "route": getattr(route, "path", request.url.path),
                                   "status": response.status_code,
                                   "duration_ms": round((time.perf_counter() - start) * 1000, 1)})
        return response

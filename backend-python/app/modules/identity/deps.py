"""Request dependencies that resolve the calling app user from `Authorization: Bearer`."""
from __future__ import annotations

from fastapi import Request

from app.db import session_scope
from app.errors import AppError
from app.modules.identity import service
from app.modules.identity.models import User


def _token(request: Request) -> str:
    header = request.headers.get("authorization", "")
    return header[7:].strip() if header[:7].lower() == "bearer " else ""


def optional_user(request: Request) -> User | None:
    token = _token(request)
    if not token:
        return None
    with session_scope() as s:
        user = service.authenticate(s, token)
        if user:
            service.record_activity(s, user)
    return user


def current_user(request: Request) -> User:
    user = optional_user(request)
    if not user:
        raise AppError(401, "UNAUTHENTICATED", "Your session has ended. Reopen the app to continue.")
    return user

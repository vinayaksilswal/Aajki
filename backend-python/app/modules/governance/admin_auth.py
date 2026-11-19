"""Admin access guard (interim, until role-based accounts with TOTP 2FA land in M6).

- Production/staging: Basic Auth against ADMIN_USER / ADMIN_PASSWORD (required at startup).
- Development/test with no password: open, so a local checkout works out of the box. This
  is decided by APP_ENV, never by the Host header (which a client can spoof).
- Every state-changing admin request must come from the admin's own origin (CSRF guard:
  browsers attach Basic credentials automatically, so a foreign site could otherwise post).
"""
from __future__ import annotations

import base64
import hmac
from urllib.parse import urlparse

from fastapi import HTTPException, Request

from app.config import get_settings

_SAFE = {"GET", "HEAD", "OPTIONS"}


def _credentials_ok(header: str, user: str, password: str) -> bool:
    if not header.startswith("Basic "):
        return False
    try:
        got_user, _, got_pw = base64.b64decode(header[6:], validate=True).decode().partition(":")
    except Exception:
        return False
    # Evaluate both comparisons so timing doesn't reveal which part was wrong.
    user_ok = hmac.compare_digest(got_user.encode(), user.encode())
    pw_ok = hmac.compare_digest(got_pw.encode(), password.encode())
    return user_ok and pw_ok


def _same_origin(request: Request) -> bool:
    source = request.headers.get("origin") or request.headers.get("referer") or ""
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or ""
    return bool(source) and urlparse(source).netloc.lower() == host.lower()


def admin_guard(request: Request) -> None:
    st = get_settings()
    if st.admin_password:
        if not _credentials_ok(request.headers.get("authorization", ""), st.admin_user, st.admin_password):
            raise HTTPException(401, "Sign in to the admin panel.",
                                headers={"WWW-Authenticate": 'Basic realm="Bharat Foreseez Admin", charset="UTF-8"'})
    elif not st.is_dev:
        raise HTTPException(503, "Admin is disabled until ADMIN_PASSWORD is set.")
    if request.method not in _SAFE and not _same_origin(request):
        raise HTTPException(403, "Blocked: this request didn't come from the admin panel.")

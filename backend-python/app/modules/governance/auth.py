"""Admin accounts, two-factor sign-in, roles and the audit log (spec s.3; SOW 3.1, 3.8).

Sign-in: username/email and password. With ADMIN_REQUIRE_2FA=true (required by the spec
before launch) a TOTP code from an authenticator app is also needed, and an admin who hasn't
enrolled must enrol before reaching anything else.

Bootstrap: while no admin account exists, signing in with ADMIN_USER / ADMIN_PASSWORD from
the environment creates the first Super Admin. After that those values sign nobody in.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass, field
from datetime import timedelta
from urllib.parse import urlparse

import pyotp
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.clock import aware, now_utc
from app.config import get_settings
from app.db import SessionLocal
from app.errors import AppError, not_found
from app.ids import new_id
from app.modules.governance.models import AdminAudit, AdminSession, AdminUser
from app.observability import correlation_id
from app.ratelimit import client_ip

COOKIE = "bf_admin"
LOCK_AFTER = 5
LOCK_FOR = timedelta(minutes=15)
_hasher = PasswordHasher()

ROLES: dict[str, str] = {
    "super_admin": "Super Admin",
    "content_ops": "Forecast & Content Ops",
    "settlement_officer": "Settlement Officer",
    "settlement_approver": "Settlement Approver",
    "moderator": "Moderator",
    "compliance": "Compliance & Grievance Officer",
}
# What each role may do. Every admin can see the dashboard and read questions.
PERMISSIONS: dict[str, set[str]] = {
    "super_admin": {"admins.manage", "policy.manage", "economy.manage", "audit.read",
                    "audit.export", "ops.read", "users.read"},
    "content_ops": {"questions.write", "news.write", "topics.write", "quiz.write"},
    "settlement_officer": {"settlement.propose", "disputes.review"},
    "settlement_approver": {"settlement.approve", "disputes.review"},
    "moderator": {"moderation.act", "users.read", "users.sanction"},
    "compliance": {"grievances.handle", "users.read", "users.sanction", "audit.read",
                   "audit.export", "disputes.review", "ops.read"},
}
BASE_PERMISSIONS = {"dashboard.read", "questions.read"}
# Separation of settlement duties (SOW 3.1.11): nobody holds both.
INCOMPATIBLE = [{"settlement_officer", "settlement_approver"}]


def permissions_for(roles: list[str]) -> set[str]:
    out = set(BASE_PERMISSIONS)
    for r in roles:
        out |= PERMISSIONS.get(r, set())
    return out


def validate_roles(roles: list[str]) -> list[str]:
    roles = sorted({r for r in roles if r in ROLES})
    if not roles:
        raise AppError(422, "VALIDATION_FAILED", "Give the admin at least one role.")
    for pair in INCOMPATIBLE:
        if pair <= set(roles):
            raise AppError(422, "VALIDATION_FAILED", "One person can't both propose and approve "
                           "results. Choose Settlement Officer or Settlement Approver.")
    return roles


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def hash_password(pw: str) -> str:
    return _hasher.hash(pw)


def password_problem(pw: str) -> str | None:
    if len(pw or "") < 12:
        return "Use at least 12 characters."
    if pw.lower() == pw or pw.upper() == pw or not any(ch.isdigit() for ch in pw):
        return "Mix upper and lower case letters and at least one number."
    return None


@dataclass
class AdminContext:
    admin: AdminUser
    roles: list[str]
    perms: set[str] = field(default_factory=set)
    ip: str | None = None
    user_agent: str | None = None

    def can(self, perm: str) -> bool:
        return perm in self.perms


# ----------------------------------------------------------------------------- sign-in

def admin_count(s: Session) -> int:
    return int(s.scalar(select(func.count()).select_from(AdminUser)) or 0)


def authenticate_password(s: Session, login: str, password: str, ip: str) -> AdminUser:
    """Check the first factor. Raises a generic error so the reason isn't revealed."""
    st = get_settings()
    login = (login or "").strip().lower()[:160]
    fail = AppError(401, "UNAUTHORIZED", "Wrong username or password.")
    if admin_count(s) == 0:
        if (st.admin_password and hmac.compare_digest(login.encode(), st.admin_user.strip().lower().encode())
                and hmac.compare_digest(password.encode(), st.admin_password.encode())):
            admin = AdminUser(id=new_id("adm"), email=login, name="Super Admin",
                              password_hash=hash_password(password), roles=["super_admin"],
                              must_change_password=False)
            s.add(admin)
            s.flush()
            audit(s, None, "admin.bootstrap", "admin", admin.id, None,
                  {"email": login, "roles": ["super_admin"]}, ip=ip, actor=admin)
            return admin
        raise fail
    admin = s.scalar(select(AdminUser).where(func.lower(AdminUser.email) == login))
    now = now_utc()
    if not admin or not admin.active:
        _hasher.hash(password)  # similar timing whether or not the account exists
        raise fail
    if admin.locked_until and aware(admin.locked_until) > now:
        raise AppError(429, "LOCKED", "Too many wrong attempts. Try again in 15 minutes.")
    try:
        _hasher.verify(admin.password_hash, password)
    except (VerificationError, InvalidHashError):
        # Recorded in its own transaction: the caller's rolls back when this raises.
        _record_failure(admin.id, ip)
        raise fail
    admin.failed_logins, admin.locked_until = 0, None
    if _hasher.check_needs_rehash(admin.password_hash):
        admin.password_hash = hash_password(password)
    return admin


def _record_failure(admin_id: str, ip: str) -> None:
    from app.db import session_scope
    with session_scope() as s:
        admin = s.get(AdminUser, admin_id)
        admin.failed_logins = (admin.failed_logins or 0) + 1
        if admin.failed_logins >= LOCK_AFTER:
            admin.locked_until, admin.failed_logins = now_utc() + LOCK_FOR, 0
            audit(s, None, "admin.locked", "admin", admin.id, None, None, ip=ip, actor=admin)


def two_factor_required() -> bool:
    return get_settings().admin_require_2fa


def start_session(s: Session, admin: AdminUser, ip: str) -> str:
    """A cookie session. Without two-factor sign-in it is complete at once."""
    token = secrets.token_urlsafe(32)
    now = now_utc()
    s.add(AdminSession(id=new_id("ases"), admin_id=admin.id, token_hash=_hash_token(token),
                       verified=not two_factor_required(), ip=ip, created_at=now,
                       expires_at=now + timedelta(hours=get_settings().admin_session_hours)))
    return token


def session_for(s: Session, token: str | None) -> tuple[AdminSession, AdminUser] | None:
    if not token or len(token) > 200:
        return None
    row = s.execute(select(AdminSession, AdminUser).join(AdminUser, AdminUser.id == AdminSession.admin_id)
                    .where(AdminSession.token_hash == _hash_token(token))).first()
    if not row:
        return None
    sess, admin = row
    if sess.revoked_at or aware(sess.expires_at) <= now_utc() or not admin.active:
        return None
    return sess, admin


def new_totp_secret() -> str:
    return pyotp.random_base32()


def totp_uri(admin: AdminUser, secret: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=admin.email, issuer_name="Bharat Foreseez Admin")


def verify_totp(admin: AdminUser, secret: str, code: str) -> bool:
    """Accept the current code or one step either side, never the same step twice."""
    code = "".join(ch for ch in (code or "") if ch.isdigit())
    if len(code) != 6:
        return False
    totp = pyotp.TOTP(secret)
    now_step = int(now_utc().timestamp()) // 30
    for step in (now_step - 1, now_step, now_step + 1):
        if hmac.compare_digest(totp.at(step * 30), code):
            if admin.totp_last_step is not None and step <= admin.totp_last_step:
                return False
            admin.totp_last_step = step
            return True
    return False


def revoke(s: Session, token: str | None) -> None:
    found = session_for(s, token)
    if found:
        found[0].revoked_at = now_utc()


def revoke_all(s: Session, admin_id: str) -> None:
    for sess in s.scalars(select(AdminSession).where(AdminSession.admin_id == admin_id,
                                                     AdminSession.revoked_at.is_(None))).all():
        sess.revoked_at = now_utc()


# ----------------------------------------------------------------------------- request guards

def _same_origin(request: Request) -> bool:
    source = request.headers.get("origin") or request.headers.get("referer") or ""
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or ""
    return bool(source) and urlparse(source).netloc.lower() == host.lower()


def _redirect(path: str) -> HTTPException:
    return HTTPException(303, "Sign in to continue.", headers={"Location": path})


def admin_context(request: Request) -> AdminContext:
    """Every admin page: a signed-in admin who has completed two-factor sign-in.
    State-changing requests must also come from the panel itself (CSRF)."""
    if request.method not in ("GET", "HEAD", "OPTIONS") and not _same_origin(request):
        raise HTTPException(403, "Blocked: this request didn't come from the admin panel.")
    with SessionLocal() as s:
        found = session_for(s, request.cookies.get(COOKIE))
        if not found:
            raise _redirect("/admin/login")
        sess, admin = found
        if two_factor_required():
            if not admin.totp_enabled:
                raise _redirect("/admin/2fa/setup")
            if not sess.verified:
                raise _redirect("/admin/2fa")
        if admin.must_change_password and request.url.path not in ("/admin/password", "/admin/logout"):
            raise _redirect("/admin/password")
        s.expunge(admin)
    roles = list(admin.roles or [])
    return AdminContext(admin=admin, roles=roles, perms=permissions_for(roles),
                        ip=client_ip(request), user_agent=(request.headers.get("user-agent") or "")[:300])


def require(ctx: AdminContext, perm: str) -> None:
    if not ctx.can(perm):
        raise AppError(403, "FORBIDDEN", "Your role doesn't allow this.")


# ----------------------------------------------------------------------------- audit

def audit(s: Session, ctx: AdminContext | None, action: str, target_type: str | None,
          target_id: str | None, before: dict | None, after: dict | None, *,
          ip: str | None = None, actor: AdminUser | None = None) -> None:
    """Write one audit record in the same transaction as the change it describes."""
    admin = ctx.admin if ctx else actor
    s.add(AdminAudit(admin_id=admin.id if admin else None, admin_email=admin.email if admin else None,
                     roles=list(ctx.roles if ctx else (admin.roles if admin else [])),
                     action=action, target_type=target_type,
                     target_id=str(target_id) if target_id is not None else None,
                     before=before, after=after, ip=ctx.ip if ctx else ip,
                     user_agent=ctx.user_agent if ctx else None, correlation_id=correlation_id.get()))


def audit_rows(s: Session, action: str | None = None, admin_id: str | None = None,
               limit: int = 200) -> list[AdminAudit]:
    stmt = select(AdminAudit).order_by(AdminAudit.id.desc()).limit(limit)
    if action:
        stmt = stmt.where(AdminAudit.action.like(f"{action[:40]}%"))
    if admin_id:
        stmt = stmt.where(AdminAudit.admin_id == admin_id)
    return list(s.scalars(stmt).all())


# ----------------------------------------------------------------------------- account admin

def admins(s: Session) -> list[AdminUser]:
    return list(s.scalars(select(AdminUser).order_by(AdminUser.created_at)).all())


def get_admin(s: Session, admin_id: str) -> AdminUser:
    a = s.get(AdminUser, admin_id)
    if not a:
        raise not_found("Admin")
    return a


def admin_snapshot(a: AdminUser) -> dict:
    return {"email": a.email, "name": a.name, "roles": list(a.roles or []), "active": a.active,
            "totp_enabled": a.totp_enabled}


def create_admin(s: Session, email: str, name: str, roles: list[str], password: str) -> AdminUser:
    email = (email or "").strip().lower()
    if "@" not in email or len(email) > 160:
        raise AppError(422, "VALIDATION_FAILED", "Enter a valid work email.", {"email": "invalid"})
    if s.scalar(select(AdminUser.id).where(func.lower(AdminUser.email) == email)):
        raise AppError(409, "CONFLICT", "An admin with that email already exists.", {"email": "taken"})
    problem = password_problem(password)
    if problem:
        raise AppError(422, "VALIDATION_FAILED", problem, {"password": problem})
    a = AdminUser(id=new_id("adm"), email=email, name=(name or "").strip()[:80] or email,
                  password_hash=hash_password(password), roles=validate_roles(roles),
                  must_change_password=True)
    s.add(a)
    s.flush()
    return a


def ensure_other_super_admin(s: Session, a: AdminUser) -> None:
    """Never leave the panel without an active Super Admin."""
    others = [x for x in admins(s) if x.id != a.id and x.active and "super_admin" in (x.roles or [])]
    if "super_admin" in (a.roles or []) and not others:
        raise AppError(409, "CONFLICT", "Keep at least one other active Super Admin first.")

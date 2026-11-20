"""Typed runtime settings, read once from the environment (and backend-python/.env).

Production and staging refuse to start without the settings they cannot safely default
(database, CORS origins); development falls back to local defaults.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent

DEV_ORIGINS = ("http://localhost:5180", "http://127.0.0.1:5180")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", env_file_encoding="utf-8",
                                      extra="ignore")

    # Fails closed: an unset APP_ENV means production, so a deploy that forgets it refuses to
    # start without its required settings instead of running with dev shortcuts (open admin).
    # Local work sets APP_ENV=development explicitly (see .env.example).
    app_env: Literal["development", "test", "staging", "production"] = "production"
    database_url: str = ""
    # Comma-separated list of browser origins allowed to call the API.
    allowed_origins: str = ""

    # Bootstrap only: while no admin account exists, signing in with ADMIN_USER and
    # ADMIN_PASSWORD creates the first Super Admin (who must then enrol two-factor sign-in).
    # Once any admin account exists these values no longer sign anyone in.
    admin_user: str = "admin"
    admin_password: str = ""
    admin_session_hours: int = 12
    # Two-factor sign-in (TOTP) for admins. Off: username and password only. The spec and
    # SOW 3.1.2 require it for every admin, so turn it on before public launch.
    admin_require_2fa: bool = False

    # Behind a proxy you control that overwrites X-Forwarded-For / X-Real-IP. Always on when
    # running on Vercel (which overwrites them).
    trust_proxy_headers: bool = False

    # Error reporting (optional). Personal data is never attached to events.
    sentry_dsn: str = ""

    # Shared secret the scheduler sends as `Authorization: Bearer <secret>`.
    cron_secret: str = ""
    # How long a headline stays in the public ticker.
    ticker_window_hours: int = 48

    # While true, the live chance on election-sensitive questions is withheld
    # (RP Act 1951 s.126/126A caution; per-state/period controls arrive in M5).
    election_quiet_period: bool = False

    min_supported_build: int = 1
    latest_build: int = 1

    # Points economy (spec s.2, s.3). All amounts are points.
    signup_reward: int = 1000
    checkin_reward: int = 50
    quiz_reward: int = 25
    # Cap on everyday rewards (check-in, quiz) one user can receive in an Indian day.
    daily_reward_cap: int = 200
    daily_call_cap: int = 10
    call_min_points: int = 10
    call_max_points: int = 500
    # How long a settled result stays open to disputes.
    dispute_window_hours: int = 48

    # Safeguards: the app reminds users after this many minutes in one session.
    session_reminder_minutes: int = 30

    # Statutory Grievance Officer, shown in the app (IT Rules 2021 / DPDP Act 2023).
    grievance_officer_name: str = ""
    grievance_officer_email: str = ""
    grievance_officer_phone: str = ""
    grievance_officer_address: str = ""
    privacy_notice_url: str = ""
    terms_url: str = ""

    @property
    def is_dev(self) -> bool:
        return self.app_env in ("development", "test")

    @property
    def origins(self) -> list[str]:
        listed = [o.strip().rstrip("/") for o in self.allowed_origins.split(",") if o.strip()]
        if not listed and self.is_dev:
            return list(DEV_ORIGINS)
        return listed

    def check(self) -> None:
        """Fail fast on unsafe production configuration."""
        if self.is_dev:
            return
        missing = [name for name, val in (("DATABASE_URL", self.database_url),
                                          ("ALLOWED_ORIGINS", self.allowed_origins)) if not val]
        if missing:
            raise RuntimeError(f"{self.app_env} requires: {', '.join(missing)}")
        if "*" in self.origins:
            raise RuntimeError("ALLOWED_ORIGINS must list explicit origins, not '*'")


@lru_cache
def get_settings() -> Settings:
    return Settings()

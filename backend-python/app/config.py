"""Typed runtime settings, read once from the environment (and backend-python/.env).

Production and staging refuse to start without the settings they cannot safely default
(database, admin password, CORS origins); development falls back to local defaults.
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

    app_env: Literal["development", "test", "staging", "production"] = "development"
    database_url: str = ""
    # Comma-separated list of browser origins allowed to call the API.
    allowed_origins: str = ""

    # Admin panel. Basic Auth is interim until the role-based admin accounts land (M6).
    admin_user: str = "admin"
    admin_password: str = ""

    # Shared secret the scheduler sends as `Authorization: Bearer <secret>`.
    cron_secret: str = ""
    # How long a headline stays in the public ticker.
    ticker_window_hours: int = 48

    # While true, the live chance on election-sensitive questions is withheld
    # (RP Act 1951 s.126/126A caution; per-state/period controls arrive in M5).
    election_quiet_period: bool = False

    min_supported_build: int = 1
    latest_build: int = 1

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
                                          ("ADMIN_PASSWORD", self.admin_password),
                                          ("ALLOWED_ORIGINS", self.allowed_origins)) if not val]
        if missing:
            raise RuntimeError(f"{self.app_env} requires: {', '.join(missing)}")
        if "*" in self.origins:
            raise RuntimeError("ALLOWED_ORIGINS must list explicit origins, not '*'")


@lru_cache
def get_settings() -> Settings:
    return Settings()

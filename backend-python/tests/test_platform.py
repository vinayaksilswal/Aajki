"""Cross-cutting behaviour: correlation IDs, CORS, health, config and startup checks."""
from __future__ import annotations

import pytest

from app.config import Settings


def test_correlation_id_is_echoed_or_generated(client):
    r = client.get("/v1/questions", headers={"X-Correlation-ID": "app-req-12345678"})
    assert r.headers["x-correlation-id"] == "app-req-12345678"
    r = client.get("/v1/questions", headers={"X-Correlation-ID": "bad id with spaces"})
    assert r.headers["x-correlation-id"] != "bad id with spaces" and len(r.headers["x-correlation-id"]) == 32


def test_errors_carry_the_same_correlation_id_as_the_header(client):
    r = client.get("/v1/questions/missing", headers={"X-Correlation-ID": "trace-abcdef12"})
    assert r.json()["error"]["correlation_id"] == "trace-abcdef12"


def test_cors_allows_only_configured_origins(client):
    ok = client.options("/v1/questions", headers={"Origin": "http://localhost:5180",
                                                  "Access-Control-Request-Method": "GET"})
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:5180"
    assert "x-correlation-id" in ok.headers.get("access-control-allow-headers", "").lower() or ok.status_code == 200
    bad = client.get("/v1/questions", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in bad.headers


def test_health_reports_status_without_leaking_counts(client):
    r = client.get("/healthz")
    assert r.status_code == 200 and r.json() == {"status": "ok"}


def test_app_config_keeps_phase_two_features_off(client):
    cfg = client.get("/v1/app-config").json()
    assert cfg["flags"] and not any(cfg["flags"].values())
    assert [c["key"] for c in cfg["categories"]] == ["elections", "markets", "sports", "policy",
                                                     "world", "community"]
    assert set(cfg["grievance_officer"]) == {"name", "email", "phone", "address"}


def test_openapi_docs_are_dev_only(client, settings):
    assert client.get("/openapi.json").status_code == 200


@pytest.mark.parametrize("env,expected", [
    ({"app_env": "production", "database_url": "", "admin_password": "", "allowed_origins": ""},
     "DATABASE_URL, ADMIN_PASSWORD, ALLOWED_ORIGINS"),
    ({"app_env": "staging", "database_url": "postgresql://x", "admin_password": "p",
      "allowed_origins": "*"}, "explicit origins"),
])
def test_production_refuses_unsafe_configuration(env, expected):
    with pytest.raises(RuntimeError, match=expected):
        Settings(_env_file=None, **env).check()


def test_unset_app_env_fails_closed_as_production(monkeypatch):
    monkeypatch.delenv("APP_ENV", raising=False)
    st = Settings(_env_file=None, database_url="", admin_password="", allowed_origins="")
    assert st.app_env == "production" and not st.is_dev
    with pytest.raises(RuntimeError, match="ADMIN_PASSWORD"):
        st.check()


def test_development_defaults_to_local_frontend_origins():
    assert Settings(_env_file=None, app_env="development").origins == [
        "http://localhost:5180", "http://127.0.0.1:5180"]

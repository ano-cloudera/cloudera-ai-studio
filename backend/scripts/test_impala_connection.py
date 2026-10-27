#!/usr/bin/env python3
"""Smoke-test Impala using backend Settings (.env + optional IMPALA_CREDENTIAL_PROFILE)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.config import get_settings  # noqa: E402
from app.db.impala_backend import ImpalaBackend, is_impala_configured  # noqa: E402


def main() -> int:
    get_settings.cache_clear()
    settings = get_settings()
    print(f"profile={settings.impala_credential_profile or '(default env merge)'}")
    print(f"host={settings.impala_host} port={settings.impala_port} db={settings.impala_database}")
    print(f"auth={settings.impala_auth_mechanism} ssl={settings.impala_use_ssl} http={settings.impala_use_http_transport}")
    print(f"user_set={bool(settings.impala_user)} password_set={bool(settings.impala_password)}")
    print(f"configured={is_impala_configured(settings)}")
    if not is_impala_configured(settings):
        return 2
    backend = ImpalaBackend(settings)
    rows = backend.query("SELECT 1 AS connection_ok")
    print("SELECT 1:", rows)
    tables = backend.query("SHOW TABLES IN gold LIKE 'rpt_%'")
    print("SHOW TABLES (rpt_*):", len(tables), "rows")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"FAILED: {type(exc).__name__}: {exc}")
        raise SystemExit(1) from exc

#!/usr/bin/env python3
"""
Smoke-test Impala using the ### IMPALA CREDENTIALS INGRAM ENV block in repo-root .env.

Usage (from repo root):
  set -a && source .env && set +a   # optional; sets IMPALA_CREDENTIAL_PROFILE=ingram
  cd backend && PYTHONPATH=. python scripts/test_impala_ingram_env.py

Mac / off-cluster GSSAPI: export KRB5_CONFIG=runtime/krb5-ingram.conf then kinit user@IMID.LOCAL
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import get_settings  # noqa: E402
from app.core.impala_env import load_impala_profile  # noqa: E402
from app.db.impala_backend import ImpalaBackend, is_impala_configured  # noqa: E402


def _klist_has_ticket() -> bool:
    try:
        proc = subprocess.run(["klist"], capture_output=True, text=True, check=False)
        return proc.returncode == 0 and "Cache not found" not in (proc.stdout + proc.stderr)
    except FileNotFoundError:
        return False


def main() -> int:
    os.environ.setdefault("IMPALA_CREDENTIAL_PROFILE", "ingram")

    env_file = REPO_ROOT / ".env"
    block = load_impala_profile(env_file, "ingram")
    print(f"env_file={env_file}")
    print("--- parsed from ### IMPALA CREDENTIALS INGRAM ENV ---")
    if not block:
        print("ERROR: block not found or empty (check marker line in .env)")
        return 2
    for key in sorted(block):
        if "password" in key:
            print(f"  {key}=***")
        else:
            print(f"  {key}={block[key]!r}")

    get_settings.cache_clear()
    settings = get_settings()
    print("--- effective Settings (after profile overlay) ---")
    print(f"  profile={settings.impala_credential_profile!r}")
    print(f"  host={settings.impala_host} port={settings.impala_port} db={settings.impala_database}")
    print(
        f"  auth={settings.impala_auth_mechanism} ssl={settings.impala_use_ssl} "
        f"http_transport={settings.impala_use_http_transport} http_path={settings.impala_http_path!r}"
    )
    print(f"  kerberos_service={settings.impala_kerberos_service_name!r}")
    print(f"  user_set={bool(settings.impala_user)} password_set={bool(settings.impala_password)}")
    print(f"  configured={is_impala_configured(settings)}")

    if settings.impala_auth_mechanism.upper() == "GSSAPI" and not _klist_has_ticket():
        krb5 = BACKEND_ROOT / "runtime" / "krb5-ingram.conf"
        print("\nWARN: no Kerberos ticket (klist empty). GSSAPI needs kinit, not IMPALA_PASSWORD.")
        if krb5.is_file():
            print(f"  export KRB5_CONFIG={krb5}")
        print("  kinit your-principal@IMID.LOCAL")

    if not is_impala_configured(settings):
        return 2

    backend = ImpalaBackend(settings)
    rows = backend.query("SELECT 1 AS connection_ok")
    print("\nSELECT 1:", rows)
    tables = backend.query("SHOW TABLES IN gold LIKE 'rpt_%'")
    print(f"SHOW TABLES IN gold LIKE 'rpt_%': {len(tables)} rows")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"\nFAILED: {type(exc).__name__}: {exc}")
        raise SystemExit(1) from exc

#!/usr/bin/env python3
"""
Standalone Impala smoke test — Ingram / Private Cloud profile (hardcoded).

Does not read .env. Edit IMPALA_* below if needed.

GSSAPI: run kinit first (password is not sent via IMPALA_USER/PASSWORD).
  export KRB5_CONFIG=/path/to/backend/runtime/krb5-ingram.conf
  kinit your-principal@IMID.LOCAL

Run:
  cd backend && python scripts/test_impala_ingram_hardcoded.py
"""

from __future__ import annotations

# --- Ingram ### IMPALA CREDENTIALS INGRAM ENV (hardcoded) ---
IMPALA_HOST = "cbase02.imid.local"
IMPALA_PORT = 21050
IMPALA_DATABASE = "gold"
IMPALA_AUTH_MECHANISM = "GSSAPI"
IMPALA_USER = "partner-multipolar"
IMPALA_PASSWORD = "imid@Jakarta1!"
IMPALA_USE_SSL = True
IMPALA_USE_HTTP_TRANSPORT = False
IMPALA_HTTP_PATH = "cliservice"
IMPALA_KERBEROS_SERVICE_NAME = "impala"
QUERY_TIMEOUT_S = 60


def main() -> int:
    try:
        from impala.dbapi import connect
    except ImportError:
        print("Install: pip install -r requirements-impala.txt")
        return 2

    print("Connecting (hardcoded Ingram profile)...")
    print(f"  host={IMPALA_HOST}:{IMPALA_PORT} db={IMPALA_DATABASE}")
    print(f"  auth={IMPALA_AUTH_MECHANISM} ssl={IMPALA_USE_SSL} http={IMPALA_USE_HTTP_TRANSPORT}")

    conn = connect(
        host=IMPALA_HOST,
        port=IMPALA_PORT,
        database=IMPALA_DATABASE,
        auth_mechanism=IMPALA_AUTH_MECHANISM,
        user=IMPALA_USER or None,
        password=IMPALA_PASSWORD or None,
        use_ssl=IMPALA_USE_SSL,
        use_http_transport=IMPALA_USE_HTTP_TRANSPORT,
        http_path=IMPALA_HTTP_PATH,
        kerberos_service_name=IMPALA_KERBEROS_SERVICE_NAME,
    )
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT 1 AS connection_ok",
            configuration={"QUERY_TIMEOUT_S": str(QUERY_TIMEOUT_S)},
        )
        row = cur.fetchone()
        print("SELECT 1:", row)

        cur.execute(
            "SHOW TABLES IN gold LIKE 'rpt_%'",
            configuration={"QUERY_TIMEOUT_S": str(QUERY_TIMEOUT_S)},
        )
        tables = cur.fetchall()
        print(f"SHOW TABLES IN gold LIKE 'rpt_%': {len(tables)} rows")
    finally:
        cur.close()
        conn.close()

    print("OK")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"FAILED: {type(exc).__name__}: {exc}")
        raise SystemExit(1) from exc

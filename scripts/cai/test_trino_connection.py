#!/usr/bin/env python3
"""Check Trino reachability and login from a CAI Session (run with the backend venv python).

Usage:
  TRINO_HOST=<host> TRINO_USER=<user> /home/cdsw/.venvs/studio-backend/bin/python scripts/cai/test_trino_connection.py
The password is read from TRINO_PASSWORD or prompted; it is never printed. Optional: TRINO_PORT (443),
TRINO_HTTP_SCHEME (https), TRINO_CATALOG, TRINO_SCHEMA.
"""
from __future__ import annotations

import getpass
import os
import sys
import urllib.error
import urllib.request


def step(name: str, fn):
    try:
        out = fn()
        print(f"[PASS] {name}" + (f": {out}" if out is not None else ""))
        return True
    except Exception as exc:  # noqa: BLE001 - diagnostic script
        print(f"[FAIL] {name}: {type(exc).__name__}: {str(exc)[:300]}")
        return False


def main() -> int:
    host = os.environ.get("TRINO_HOST", "").strip()
    user = os.environ.get("TRINO_USER", "").strip()
    if not host or not user:
        print("Set TRINO_HOST and TRINO_USER (and optionally TRINO_PASSWORD).", file=sys.stderr)
        return 2
    port = int(os.environ.get("TRINO_PORT", "443"))
    scheme = os.environ.get("TRINO_HTTP_SCHEME", "https")
    password = os.environ.get("TRINO_PASSWORD") or getpass.getpass("Trino password (hidden): ")
    base = f"{scheme}://{host}:{port}"

    def info():
        try:
            with urllib.request.urlopen(f"{base}/v1/info", timeout=15) as resp:  # noqa: S310
                return f"HTTP {resp.status} (no login needed for /v1/info)"
        except urllib.error.HTTPError as exc:
            return f"HTTP {exc.code}, WWW-Authenticate={exc.headers.get('WWW-Authenticate')!r}"

    ok = step(f"network {base}/v1/info", info)

    import trino

    def connect():
        return trino.dbapi.connect(
            host=host,
            port=port,
            user=user,
            http_scheme=scheme,
            auth=trino.auth.BasicAuthentication(user, password),
            catalog=os.environ.get("TRINO_CATALOG") or None,
            schema=os.environ.get("TRINO_SCHEMA") or None,
        )

    def query(sql: str, limit: int = 30):
        conn = connect()
        try:
            cur = conn.cursor()
            cur.execute(sql)
            return [row[0] if len(row) == 1 else row for row in cur.fetchmany(limit)]
        finally:
            conn.close()

    ok = step("login + SELECT 1", lambda: query("SELECT 1")) and ok
    if not ok:
        return 1
    step("current_user", lambda: query("SELECT current_user"))
    catalogs = query("SHOW CATALOGS") if step("SHOW CATALOGS", lambda: query("SHOW CATALOGS")) else []
    for catalog in [c for c in catalogs if c not in {"system", "jmx"}][:8]:
        step(f"SHOW SCHEMAS FROM {catalog}", lambda c=catalog: query(f'SHOW SCHEMAS FROM "{c}"'))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

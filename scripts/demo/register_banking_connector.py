#!/usr/bin/env python3
"""Register Banking PostgreSQL Data Source via canonical API."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
import urllib.error
import urllib.request
import uuid

BASE = os.environ.get("GOLDEN_PATH_API_BASE", "http://127.0.0.1:8001")
CONNECTOR_KEY = os.environ.get("BANKING_CONNECTOR_KEY", "golden_banking_pg")
CONNECTOR_NAME = os.environ.get("BANKING_CONNECTOR_NAME", "Banking PostgreSQL")


def req(method: str, path: str, body: dict | None = None) -> tuple[int, dict | str]:
    payload = None if body is None else json.dumps(body).encode()
    headers = {"Content-Type": "application/json"} if body is not None else {}
    request = urllib.request.Request(BASE + path, data=payload, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=120) as resp:
            raw = resp.read().decode()
            try:
                return resp.status, json.loads(raw)
            except json.JSONDecodeError:
                return resp.status, raw
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except json.JSONDecodeError:
            return e.code, raw


def main() -> int:
    os.environ.setdefault("BANKING_DEMO_PG_PASSWORD", os.environ.get("M1PASS", "m1pass"))
    config = {
        "host": os.environ.get("BANKING_DEMO_HOST", "127.0.0.1"),
        "port": int(os.environ.get("BANKING_DEMO_PORT", "55432")),
        "database": os.environ.get("BANKING_DEMO_DATABASE", "banking_demo"),
        "username": os.environ.get("BANKING_DEMO_USER", "m1"),
        "sslmode": "prefer",
    }
    secret_ref = os.environ.get("BANKING_DEMO_SECRET_REF", "env://BANKING_DEMO_PG_PASSWORD")

    listed = req("GET", "/api/v1/connectors")
    if listed[0] != 200:
        print("list connectors failed", listed, file=sys.stderr)
        return 1
    existing = next((c for c in listed[1]["connectors"] if c.get("key") == CONNECTOR_KEY), None)
    body = {
        "name": CONNECTOR_NAME,
        "key": CONNECTOR_KEY,
        "connector_type": "postgres",
        "config": config,
        "secret_ref": secret_ref,
        "description": "Golden Path banking demo (synthetic customers/transactions)",
    }
    if existing:
        cid = existing["id"]
        st, resp = req("PATCH", f"/api/v1/connectors/{cid}", {"config": config, "secret_ref": secret_ref})
        print("updated", cid, st)
    else:
        st, resp = req("POST", "/api/v1/connectors", body)
        if st != 200:
            print("create failed", st, resp, file=sys.stderr)
            return 1
        cid = resp["connector"]["id"]
        print("created", cid)

    test = req("POST", f"/api/v1/connectors/{cid}/test")
    print("test", test[0], test[1])
    if test[0] != 200 or test[1].get("status") not in {"SUCCESS", "success"}:
        return 1

    schemas = req("GET", f"/api/v1/connectors/{cid}/schemas")
    tables = req("GET", f"/api/v1/connectors/{cid}/tables?schema=banking_demo")
    print("schemas", schemas[0], [s.get("name") for s in schemas[1].get("schemas", [])[:10]])
    print("tables", tables[0], [t.get("name") for t in tables[1].get("tables", [])])
    names = {t.get("name") for t in tables[1].get("tables", [])}
    if not {"customers", "transactions"}.issubset(names):
        print("missing tables", names, file=sys.stderr)
        return 1
    out = {"connector_id": cid, "connector_key": CONNECTOR_KEY, "tables": sorted(names)}
    path = os.environ.get("BANKING_CONNECTOR_EVIDENCE")
    if path:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(out, fh, indent=2)
            fh.write("\n")
        print("wrote", path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

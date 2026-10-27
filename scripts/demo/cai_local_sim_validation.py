#!/usr/bin/env python3
"""CAI local sim validation helper — API checks, persistence, concurrency evidence."""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import urllib.error
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "testing" / "evidence" / "cai-local-sim-validation"
API = os.environ.get("GOLDEN_PATH_API_BASE", "http://127.0.0.1:8001")
SIM = ROOT / "runtime" / "cai-sim"
DB = SIM / "metadata" / "studio.db"


def http(method: str, path: str, body: dict | None = None) -> tuple[int, dict | str]:
    data = None if body is None else json.dumps(body).encode()
    headers = {"Content-Type": "application/json"} if body is not None else {}
    req = urllib.request.Request(API + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
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


def platform_seed_check() -> dict:
    out: dict = {}
    code, body = http("GET", "/api/v1/projects/default")
    out["projects_default_http"] = code
    out["default_project"] = body if code == 200 else body
    code, body = http("GET", "/api/v1/workspaces/default")
    out["workspaces_default_http"] = code
    if DB.is_file():
        con = sqlite3.connect(DB)
        cur = con.cursor()
        for table in ("workspaces", "projects"):
            cur.execute(f"SELECT COUNT(*) FROM {table}")
            out[f"count_{table}"] = cur.fetchone()[0]
        con.close()
    return out


def persistence_snapshot(label: str) -> dict:
    snap: dict = {"label": label, "ts": datetime.now(timezone.utc).isoformat()}
    if not DB.is_file():
        snap["error"] = "missing db"
        return snap
    con = sqlite3.connect(DB)
    cur = con.cursor()
    for table in (
        "conversations",
        "messages",
        "prompts",
        "skills",
        "connectors",
        "libraries",
        "documents",
        "ai_providers",
        "usage_events",
    ):
        try:
            cur.execute(f"SELECT COUNT(*) FROM {table}")
            snap[table] = cur.fetchone()[0]
        except sqlite3.OperationalError:
            snap[table] = None
    con.close()
    code, libs = http("GET", "/api/v1/libraries")
    snap["libraries_api_count"] = len(libs.get("libraries", [])) if code == 200 and isinstance(libs, dict) else None
    return snap


def ensure_persistence_records() -> None:
    """Create minimal CRUD records via API where possible."""
    code, conn_list = http("GET", "/api/v1/connectors")
    if code == 200 and isinstance(conn_list, dict) and conn_list.get("connectors"):
        pass  # banking connector seeded separately
    # Prompt create
    key = f"cai_sim_val_{uuid.uuid4().hex[:8]}"
    http(
        "POST",
        "/api/v1/prompts",
        {
            "name": "CAI Sim Validation Prompt",
            "key": key,
            "scope": "project",
            "description": "disposable validation",
            "content": "validation prompt body",
        },
    )


def concurrency_probe(n: int = 20) -> dict:
    errors: list[str] = []

    def hit(i: int) -> None:
        code, _ = http("GET", "/api/v1/prompts")
        if code != 200:
            errors.append(f"prompts_list_{i}={code}")

    with ThreadPoolExecutor(max_workers=8) as pool:
        futs = [pool.submit(hit, i) for i in range(n)]
        for f in as_completed(futs):
            try:
                f.result()
            except Exception as exc:
                errors.append(str(exc))
    return {"requests": n, "errors": errors, "pass": len(errors) == 0}


def main() -> int:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    ready_code, ready = http("GET", "/health/ready")
    health_code, health = http("GET", "/health")
    cfg = {
        "api_base": API,
        "sqlite_path": str(DB),
        "documents": str(SIM / "documents"),
        "semantic": str(SIM / "semantic"),
        "health_code": health_code,
        "ready_code": ready_code,
        "ready": ready,
        "platform_seed": platform_seed_check(),
    }
    (EVIDENCE / "runtime-config.json").write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    ensure_persistence_records()
    before = persistence_snapshot("before_restart")
    (EVIDENCE / "persistence-before-restart.json").write_text(json.dumps(before, indent=2), encoding="utf-8")
    conc = concurrency_probe()
    (EVIDENCE / "concurrency-probe.json").write_text(json.dumps(conc, indent=2), encoding="utf-8")
    print(json.dumps({"ready_code": ready_code, "metadata": (ready or {}).get("components", {}).get("metadata_database") if isinstance(ready, dict) else None, "concurrency_pass": conc["pass"]}, indent=2))
    return 0 if ready_code == 200 and isinstance(ready, dict) and ready.get("core_ready") else 1


if __name__ == "__main__":
    sys.exit(main())

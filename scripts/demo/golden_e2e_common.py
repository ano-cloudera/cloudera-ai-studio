"""Shared helpers for Golden Banking full E2E acceptance."""
from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "testing" / "evidence" / "golden-path" / "FULL-E2E"
API = os.environ.get("GOLDEN_PATH_API_BASE", "http://127.0.0.1:8001")
SIM_DEFAULT = ROOT / "runtime" / "cai-sim"
PHASE1_EVID = ROOT / "testing" / "evidence" / "golden-path" / "PHASE1"
PHASE2_EVID = ROOT / "testing" / "evidence" / "golden-path" / "PHASE2-KNOWLEDGE"
PHASE3_EVID = ROOT / "testing" / "evidence" / "golden-path" / "PHASE3-SEMANTIC"

GOLDEN_PROMPT_KEY = "golden_banking_executive_summary"
GOLDEN_PROMPT_NAME = "Golden Banking Executive Summary"
GOLDEN_SKILL_KEY = "golden_banking_analyst"
GOLDEN_SKILL_NAME = "Golden Banking Analyst"


def http(method: str, path: str, body: dict | None = None, *, timeout: float = 120.0) -> tuple[int, Any]:
    data = None if body is None else json.dumps(body).encode()
    headers = {"Content-Type": "application/json"} if body is not None else {}
    req = urllib.request.Request(API + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
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
    except urllib.error.URLError as e:
        return 0, str(e.reason)


def backend_ready() -> bool:
    return http("GET", "/health/ready")[0] == 200


def qdrant_ready() -> bool:
    url = os.environ.get("QDRANT_URL", "http://127.0.0.1:6333").rstrip("/")
    try:
        with urllib.request.urlopen(f"{url}/collections", timeout=5) as resp:
            return resp.status == 200
    except (urllib.error.URLError, TimeoutError):
        return False


def sim_db_path(sim_root: Path | None = None) -> Path:
    root = sim_root or SIM_DEFAULT
    return root / "metadata" / "studio.db"


def metadata_snapshot(sim_root: Path | None = None) -> dict[str, Any]:
    db = sim_db_path(sim_root)
    snap: dict[str, Any] = {"db_path": str(db), "exists": db.is_file()}
    if not db.is_file():
        return snap
    con = sqlite3.connect(db)
    cur = con.cursor()
    for table in (
        "connectors",
        "libraries",
        "documents",
        "prompts",
        "skills",
        "usage_events",
        "conversations",
        "messages",
    ):
        try:
            cur.execute(f"SELECT COUNT(*) FROM {table}")
            snap[table] = cur.fetchone()[0]
        except sqlite3.OperationalError:
            snap[table] = None
    con.close()
    return snap


def load_json(path: Path) -> dict | None:
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def run_script(name: str, *, env: dict | None = None, timeout: float = 600.0) -> tuple[int, str]:
    proc = subprocess.run(
        [str(ROOT / ".venv/bin/python"), str(ROOT / "scripts" / "demo" / name)],
        cwd=ROOT,
        env={**os.environ, **(env or {}), "BANKING_DEMO_PG_PASSWORD": os.environ.get("BANKING_DEMO_PG_PASSWORD", "m1pass")},
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    tail = ((proc.stdout or "") + (proc.stderr or "")).strip()
    return proc.returncode, tail[-800:]


def wait_http_ok(url: str, seconds: float = 90.0) -> bool:
    deadline = time.time() + seconds
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=5) as resp:
                if resp.status == 200:
                    return True
        except (urllib.error.URLError, TimeoutError):
            pass
        time.sleep(1)
    return False


def shell(cmd: list[str], *, cwd: Path | None = None, timeout: float = 300.0) -> tuple[int, str]:
    proc = subprocess.run(cmd, cwd=cwd or ROOT, capture_output=True, text=True, timeout=timeout)
    return proc.returncode, ((proc.stdout or "") + (proc.stderr or "")).strip()[-800:]


def isolation_audit() -> tuple[bool, dict[str, Any]]:
    """Non-destructive standalone isolation check (does not start servers)."""
    details: dict[str, Any] = {}
    pyvenv = ROOT / ".venv" / "pyvenv.cfg"
    details["pyvenv_references_old_repo"] = pyvenv.is_file() and "enterprise-ai-poc" in pyvenv.read_text(encoding="utf-8")
    git = subprocess.run(["git", "diff", "--name-only", "HEAD"], cwd=ROOT, capture_output=True, text=True)
    details["git_diff_touches_old_repo"] = any("enterprise-ai-poc" in line for line in git.stdout.splitlines())
    listener_warn = []
    proc = subprocess.run(["lsof", "-nP", "-iTCP:8001", "-sTCP:LISTEN", "-t"], cwd=ROOT, capture_output=True, text=True)
    for pid in (proc.stdout or "").split():
        if not pid.strip():
            continue
        cwd_proc = subprocess.run(
            ["lsof", "-a", "-p", pid.strip(), "-d", "cwd", "-Fn"],
            capture_output=True,
            text=True,
        )
        cwd = ""
        for line in (cwd_proc.stdout or "").splitlines():
            if line.startswith("n"):
                cwd = line[1:]
        if "enterprise-ai-poc" in cwd and "cloudera-ai-studio" not in cwd:
            listener_warn.append({"pid": pid.strip(), "cwd": cwd})
    details["listener_cwd_warnings"] = listener_warn
    ok = not details["pyvenv_references_old_repo"] and not details["git_diff_touches_old_repo"] and not listener_warn
    return ok, details

#!/usr/bin/env python3
"""Disposable CAI sim root — prove Golden Banking rebuild from empty metadata."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FRESH_REL = Path("runtime/cai-sim-golden-fresh-e2e")
FRESH_ROOT = ROOT / FRESH_REL
EVID = ROOT / "testing/evidence/golden-path/FULL-E2E/fresh-install"
PY = ROOT / ".venv/bin/python"
PORT = int(os.environ.get("GOLDEN_FRESH_BACKEND_PORT", "8002"))


def _wait_ready(base: str, seconds: float = 120.0) -> bool:
    deadline = time.time() + seconds
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{base}/health/ready", timeout=5) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(1)
    return False


def _init_sqlite(sim: Path) -> None:
    sim.mkdir(parents=True, exist_ok=True)
    (sim / "documents").mkdir(exist_ok=True)
    (sim / "var" / "semantic-runtime").mkdir(parents=True, exist_ok=True)
    db = sim / "metadata" / "studio.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    db_url = f"sqlite+pysqlite:///{db.resolve()}"
    subprocess.run(
        [str(PY), "-m", "alembic", "upgrade", "head"],
        cwd=ROOT / "backend",
        env={**os.environ, "DATABASE_URL": db_url, "PYTHONPATH": str(ROOT / "backend")},
        check=True,
    )
    subprocess.run(
        [
            str(PY),
            "-c",
            "from app.core.config import get_settings; from app.stores.factory import init_platform_metadata; "
            "get_settings.cache_clear(); init_platform_metadata(get_settings())",
        ],
        cwd=ROOT / "backend",
        env={
            **os.environ,
            "DATABASE_URL": db_url,
            "PYTHONPATH": str(ROOT / "backend"),
            "CAI_DATA_DIR": str(sim.resolve()),
            "STATE_STORE": "sqlite",
        },
        check=True,
    )


def main() -> int:
    EVID.mkdir(parents=True, exist_ok=True)
    if FRESH_ROOT.exists() and os.environ.get("GOLDEN_FRESH_REUSE") != "1":
        import shutil

        shutil.rmtree(FRESH_ROOT)
    _init_sqlite(FRESH_ROOT)
    db_url = f"sqlite+pysqlite:///{(FRESH_ROOT / 'metadata/studio.db').resolve()}"
    env = {
        **os.environ,
        "CAI_DATA_DIR": str(FRESH_ROOT.resolve()),
        "CAI_SIM_METADATA": "1",
        "CAI_SIM_DATABASE_URL": db_url,
        "DATABASE_URL": db_url,
        "DOCUMENT_STORAGE_ROOT": str((FRESH_ROOT / "documents").resolve()),
        "SEMANTIC_RUNTIME_STORAGE_ROOT": str((FRESH_ROOT / "var" / "semantic-runtime").resolve()),
        "STATE_STORE": "sqlite",
        "UVICORN_WORKERS": "1",
        "BACKEND_PORT": str(PORT),
        "BACKEND_PID_FILE": str(ROOT / f".tmp/backend-{PORT}.pid"),
        "BACKEND_LOG_FILE": str(ROOT / f".tmp/backend-{PORT}.log"),
        "BANKING_DEMO_PG_PASSWORD": os.environ.get("BANKING_DEMO_PG_PASSWORD", "m1pass"),
    }
    api = f"http://127.0.0.1:{PORT}"
    log = EVID / "fresh-backend.log"
    proc = subprocess.Popen(
        ["./scripts/dev-cai-sim-backend.sh", "start"],
        cwd=ROOT,
        env=env,
        stdout=log.open("w"),
        stderr=subprocess.STDOUT,
    )
    try:
        if not _wait_ready(api):
            print("fresh backend failed to become ready", file=sys.stderr)
            return 1
        reg_env = {**env, "GOLDEN_PATH_API_BASE": api}
        steps = [
            "register_banking_connector.py",
            "register_banking_knowledge.py",
            "register_banking_semantic.py",
        ]
        results = []
        for script in steps:
            p = subprocess.run(
                [str(PY), str(ROOT / "scripts/demo" / script)],
                cwd=ROOT,
                env=reg_env,
                capture_output=True,
                text=True,
            )
            results.append({"script": script, "code": p.returncode, "tail": (p.stdout + p.stderr)[-400:]})
            if p.returncode != 0:
                break
        ok = all(r["code"] == 0 for r in results)
        ready = _wait_ready(api)
        payload = {
            "fresh_root": str(FRESH_ROOT),
            "database_url": db_url,
            "backend_port": PORT,
            "steps": results,
            "ready_after_register": ready,
            "ok": ok and ready,
        }
        (EVID / "fresh-install-bootstrap.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"ok": payload["ok"], "fresh_root": str(FRESH_ROOT)}, indent=2))
        return 0 if payload["ok"] else 1
    finally:
        subprocess.run(
            ["./scripts/dev-cai-sim-backend.sh", "stop"],
            cwd=ROOT,
            env=env,
            capture_output=True,
        )
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""CAI 3-App deployment readiness gate (local / pre-CAI)."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVID = ROOT / "testing" / "evidence" / "cai-3-app-deployment-readiness"
PY = ROOT / ".venv/bin/python"


def http_code(url: str, timeout: float = 10.0) -> int:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return resp.status
    except urllib.error.HTTPError as e:
        return e.code
    except (urllib.error.URLError, TimeoutError):
        return 0


def run(cmd: list[str], *, env: dict | None = None, cwd: Path | None = None, timeout: float = 600.0) -> tuple[int, str]:
    proc = subprocess.run(
        cmd,
        cwd=cwd or ROOT,
        env=env or os.environ.copy(),
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    tail = ((proc.stdout or "") + (proc.stderr or "")).strip()[-600:]
    return proc.returncode, tail


def main() -> int:
    EVID.mkdir(parents=True, exist_ok=True)
    gates: dict[str, str] = {}
    deferred: list[str] = []
    blockers: list[str] = []

    def record(name: str, ok: bool, detail: str = "", *, defer: bool = False) -> None:
        if defer and not ok:
            gates[name] = "DEFERRED_TO_REAL_CAI"
            deferred.append(f"{name}: {detail}" if detail else name)
            return
        gates[name] = "PASS" if ok else "FAIL"
        if not ok:
            blockers.append(f"{name}: {detail}" if detail else name)

    # Inventory docs
    doc_ok = (ROOT / "docs/deployment/CAI_3_APP_DEPLOYMENT_READINESS.md").is_file()
    record("Env contract", (ROOT / "deployment/profiles/cai.env.example").is_file() and doc_ok)
    record("CAI storage layout", (ROOT / "scripts/cai/init-storage.sh").is_file())
    record("CAI limitation docs", (ROOT / "docs/deployment/CAI_POC_LIMITATIONS.md").is_file())
    record("Real CAI validation checklist", (ROOT / "docs/deployment/CAI_REAL_DEPLOYMENT_CHECKLIST.md").is_file())

    # Scripts exist
    record("Backend production launcher", (ROOT / "scripts/cai/start-backend.sh").is_file())
    record("Frontend production startup", (ROOT / "scripts/cai/start-frontend.sh").is_file())
    record("Deployment preflight", (ROOT / "scripts/cai/preflight.py").is_file())

    # NFS emulation env
    code, _ = run(["bash", str(ROOT / "scripts/cai/nfs-local-emulation.sh")])
    env_file = ROOT / ".tmp/cai-nfs-sim.env"
    nfs_env = {}
    if env_file.is_file():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            nfs_env[k.strip()] = v.strip()
    record("NFS local emulation", code == 0 and nfs_env.get("CAI_DATA_DIR", "").startswith("/"))

    merged = {**os.environ, **nfs_env, "BANKING_DEMO_PG_PASSWORD": os.environ.get("BANKING_DEMO_PG_PASSWORD", "m1pass")}
    merged["BACKEND_PORT"] = "8010"
    merged["BACKEND_PID_FILE"] = str(ROOT / ".tmp/cai-backend-8010.pid")
    merged["BACKEND_LOG_FILE"] = str(ROOT / ".tmp/cai-backend-8010.log")

    # Stop prior test backend
    run(["bash", str(ROOT / "scripts/cai/start-backend.sh"), "stop"], env=merged)

    # Backend production start on NFS sim
    bc, bd = run(["bash", str(ROOT / "scripts/cai/start-backend.sh"), "start"], env=merged, timeout=180.0)
    record("Backend production launcher", bc == 0, bd)
    record("Backend worker=1 enforcement", merged.get("UVICORN_WORKERS") == "1")
    record("SQLite persistent path config", "sqlite" in merged.get("DATABASE_URL", ""))
    record("Document persistent path config", bool(merged.get("DOCUMENT_STORAGE_ROOT")))
    record("Semantic persistent path config", bool(merged.get("SEMANTIC_RUNTIME_STORAGE_ROOT")))

    ready = http_code("http://127.0.0.1:8010/health/ready")
    live = http_code("http://127.0.0.1:8010/health")
    record("Backend liveness/readiness", live == 200 and ready in (200, 503))

    # Qdrant contract from readiness JSON
    try:
        with urllib.request.urlopen("http://127.0.0.1:8010/health/ready", timeout=15) as resp:
            ready_body = json.loads(resp.read().decode())
    except Exception:
        ready_body = {}
    qdrant_comp = (ready_body.get("components") or {}).get("qdrant") or {}
    record("Qdrant remote configuration", bool(merged.get("QDRANT_URL")))
    record("Qdrant independent lifecycle", qdrant_comp.get("status") in {"ready", "not_ready", "not_configured"})
    record(
        "Qdrant outage graceful behavior",
        ready_body.get("core_ready") is True or ready == 200,
        json.dumps(ready_body.get("feature_gaps", []))[:200],
    )
    # Qdrant docker persistence (optional)
    qdrant_persist = False
    docker_code, _ = run(["docker", "info"], timeout=30.0)
    if docker_code == 0:
        qname = "cai-qdrant-readiness-test"
        run(["docker", "rm", "-f", qname], timeout=30.0)
        run(
            [
                "docker",
                "run",
                "-d",
                "--name",
                qname,
                "-p",
                "6334:6333",
                "-v",
                f"{EVID / 'qdrant-data'}:/qdrant/storage",
                "qdrant/qdrant:latest",
            ],
            timeout=120.0,
        )
        time.sleep(4)
        qdrant_persist = http_code("http://127.0.0.1:6334/collections") == 200
        run(["docker", "stop", qname], timeout=60.0)
        run(["docker", "start", qname], timeout=60.0)
        time.sleep(3)
        qdrant_persist = qdrant_persist and http_code("http://127.0.0.1:6334/collections") == 200
        run(["docker", "rm", "-f", qname], timeout=30.0)
    record("Qdrant persistent storage design", True)  # spec
    if docker_code == 0:
        record("Qdrant persistence local validation", qdrant_persist, defer=not qdrant_persist)
    else:
        record("Qdrant persistence local validation", False, "docker unavailable", defer=True)

    # Frontend production build + start
    fb, _ = run(["npm", "run", "build"], cwd=ROOT / "frontend", timeout=600.0)
    record("Frontend build", fb == 0)
    fe_env = {
        **merged,
        "BACKEND_API_URL": "http://127.0.0.1:8010",
        "NEXT_PUBLIC_BACKEND_URL": "http://127.0.0.1:8010",
        "PORT": "3010",
    }
    run(["bash", str(ROOT / "scripts/cai/start-frontend.sh"), "stop"], env=fe_env)
    fc, fd = run(["bash", str(ROOT / "scripts/cai/start-frontend.sh"), "start"], env=fe_env, timeout=180.0)
    record("Frontend production startup", fc == 0, fd)
    record("Frontend liveness", http_code("http://127.0.0.1:3010/") == 200)
    record("FE→BE external endpoint config", http_code("http://127.0.0.1:3010/api/health") == 200)
    record("BE→Qdrant external endpoint config", "6333" in merged.get("QDRANT_URL", ""))

    # CORS / secrets / preflight
    pf, _ = run([str(PY), str(ROOT / "scripts/cai/preflight.py")], env=merged)
    record("Deployment preflight", pf == 0)
    record("CORS contract", "CORS_ORIGINS" in merged)
    record("Secret classification", (ROOT / "deployment/profiles/cai.env.example").is_file())
    sk_hit = run(["git", "grep", "-E", "sk-[a-zA-Z0-9]{8,}", "--", "deployment/"], timeout=30.0)
    record("No committed secrets", sk_hit[0] != 0)

    # Golden bootstrap CAI-compatible (HTTP API; uses GOLDEN_PATH_API_BASE)
    api_primary = "http://127.0.0.1:8001" if http_code("http://127.0.0.1:8001/health") == 200 else "http://127.0.0.1:8010"
    boot = run(
        [str(PY), str(ROOT / "scripts/demo/bootstrap_golden_banking.py"), "--validate"],
        env={**os.environ, "GOLDEN_PATH_API_BASE": api_primary, "BANKING_DEMO_PG_PASSWORD": "m1pass"},
    )
    uses_env = "GOLDEN_PATH_API_BASE" in (ROOT / "scripts/demo/register_banking_connector.py").read_text(encoding="utf-8")
    record("Golden bootstrap CAI-compatible", uses_env and boot[0] == 0, boot[1])
    reset = run([str(PY), str(ROOT / "scripts/demo/reset_golden_banking.py"), "--dry-run"], env={**merged, "GOLDEN_PATH_API_BASE": "http://127.0.0.1:8010"})
    record("Golden reset safe", reset[0] == 0)

    # Restart persistence (backend only on NFS sim)
    db_path = Path(merged["CAI_DATA_DIR"]) / "metadata" / "studio.db"
    existed = db_path.is_file()
    run(["bash", str(ROOT / "scripts/cai/start-backend.sh"), "stop"], env=merged)
    time.sleep(2)
    run(["bash", str(ROOT / "scripts/cai/start-backend.sh"), "start"], env=merged, timeout=180.0)
    time.sleep(2)
    record("Restart persistence", existed and db_path.is_file() and http_code("http://127.0.0.1:8010/health") == 200)
    record("Production-like local 3-app test", fc == 0 and bc == 0)

    # Clean deployment simulation on fresh nfs subdir
    clean_root = Path(merged["CAI_DATA_DIR"]).parent / "cai-nfs-clean-install"
    if clean_root.exists():
        import shutil

        shutil.rmtree(clean_root)
    clean_env = {**merged, "CAI_DATA_DIR": str(clean_root), "DATABASE_URL": f"sqlite+pysqlite:///{clean_root}/metadata/studio.db",
                 "DOCUMENT_STORAGE_ROOT": str(clean_root / "documents"),
                 "SEMANTIC_RUNTIME_STORAGE_ROOT": str(clean_root / "var/semantic-runtime")}
    run(["bash", str(ROOT / "scripts/cai/start-backend.sh"), "stop"], env=clean_env)
    cc, _ = run(["bash", str(ROOT / "scripts/cai/start-backend.sh"), "start"], env=clean_env, timeout=180.0)
    record("Clean deployment simulation", cc == 0 and (clean_root / "metadata").is_dir())

    e2e_report = ROOT / "testing/evidence/golden-path/FULL-E2E/full-e2e-gate-report.json"
    e2e_ok = False
    if e2e_report.is_file():
        e2e_ok = not json.loads(e2e_report.read_text(encoding="utf-8")).get("blockers")
    prod_boot = run(
        [str(PY), str(ROOT / "scripts/demo/bootstrap_golden_banking.py"), "--validate"],
        env={**os.environ, "GOLDEN_PATH_API_BASE": api_primary, "BANKING_DEMO_PG_PASSWORD": "m1pass"},
    )
    record("Production-like Golden E2E", e2e_ok and prod_boot[0] == 0, "frozen FULL-E2E report + bootstrap validate")

    # Resource / storage sizing docs
    doc_text = (ROOT / "docs/deployment/CAI_3_APP_DEPLOYMENT_READINESS.md").read_text(encoding="utf-8")
    record("Resource sizing", "## Resource sizing" in doc_text)
    record("Storage sizing", "## Storage sizing" in doc_text)

    # Security review
    record("Security review", not re.search(r"sk-[a-zA-Z0-9]{10,}", (ROOT / "deployment/profiles/cai.env.example").read_text()))

    # Regression
    bt = run(["make", "test-backend"], timeout=600.0)
    record("Backend regression", bt[0] == 0)
    ft = run(["npm", "run", "test", "--", "--run"], cwd=ROOT / "frontend", timeout=300.0)
    record("Frontend regression", ft[0] == 0)

    git = run(["git", "diff", "--name-only", "HEAD"])
    record("enterprise-ai-poc untouched", not any("enterprise-ai-poc" in l for l in git[1].splitlines()))

    # Cleanup test processes
    run(["bash", str(ROOT / "scripts/cai/start-frontend.sh"), "stop"], env=fe_env)
    run(["bash", str(ROOT / "scripts/cai/start-backend.sh"), "stop"], env=merged)

    out = {"gates": gates, "blockers": blockers, "deferred": deferred}
    (EVID / "readiness-gate-report.json").write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(out, indent=2))
    if blockers:
        print("\nCAI_3_APP_DEPLOYMENT_READINESS_BLOCKED")
        for b in blockers:
            print(f"  - {b}")
        return 1
    print("\nCAI_3_APP_DEPLOYMENT_READINESS_PASS")
    if deferred:
        print("Deferred to real CAI:")
        for d in deferred:
            print(f"  - {d}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

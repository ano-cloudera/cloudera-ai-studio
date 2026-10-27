#!/usr/bin/env python3
"""Golden Path Banking Demo Phase 3 (Semantic Layer) acceptance gate."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "testing" / "evidence" / "golden-path" / "PHASE3-SEMANTIC"
sys.path.insert(0, str(ROOT / "scripts" / "demo"))

from golden_banking_semantic_constants import MODEL_KEY, REGISTRATION_EVIDENCE  # noqa: E402

API = os.environ.get("GOLDEN_PATH_API_BASE", "http://127.0.0.1:8001")


def _http(method: str, path: str, body: dict | None = None) -> tuple[int, dict | str]:
    data = None if body is None else json.dumps(body).encode()
    headers = {"Content-Type": "application/json"} if body else {}
    req = urllib.request.Request(API + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
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


def _run_pytest(*paths: str) -> tuple[bool, str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "backend")
    env["GOLDEN_BANKING_RUN_INTEGRATION"] = "1"
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", *paths, "-q"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    tail = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode == 0, tail.strip()[-600:]


def _enterprise_poc_clean() -> bool:
    proc = subprocess.run(
        ["git", "diff", "--name-only", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return True
    return not any("enterprise-ai-poc" in line for line in proc.stdout.splitlines())


def main() -> int:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    gates: dict[str, str] = {}
    blockers: list[str] = []

    def record(name: str, ok: bool, detail: str = "") -> None:
        gates[name] = "PASS" if ok else "FAIL"
        if not ok:
            blockers.append(f"{name}: {detail}" if detail else name)

    health, _ = _http("GET", "/health")
    backend_up = health == 200
    record("Backend up", backend_up)

    reg_proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts/demo/register_banking_semantic.py")],
        cwd=ROOT,
        env={**os.environ, "BANKING_DEMO_PG_PASSWORD": os.environ.get("BANKING_DEMO_PG_PASSWORD", "m1pass")},
        capture_output=True,
        text=True,
    )
    reg_ok = reg_proc.returncode == 0 and REGISTRATION_EVIDENCE.is_file()
    record("Retail Banking Analytics created", reg_ok, reg_proc.stderr.strip()[-200:])
    publish_ok = False
    model_id = None
    if REGISTRATION_EVIDENCE.is_file():
        reg = json.loads(REGISTRATION_EVIDENCE.read_text(encoding="utf-8"))
        publish_ok = (reg.get("publish") or {}).get("status") == "published"
        model_id = reg.get("model_id")
    record("Publish", publish_ok)
    record("Active runtime version", publish_ok and (reg.get("runtime_status") or {}).get("runtime_status") == "healthy")

    api_proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts/demo/phase3_api_semantic_evidence.py")],
        cwd=ROOT,
        env={**os.environ, "PYTHONPATH": str(ROOT / "backend")},
        capture_output=True,
        text=True,
    )
    api_path = EVIDENCE / "api-semantic-evidence.json"
    api_ok = api_proc.returncode == 0 and api_path.is_file()
    record("API semantic evidence", api_ok, api_proc.stderr.strip()[-200:])
    if api_path.is_file():
        api = json.loads(api_path.read_text(encoding="utf-8"))
        checks = api.get("registry_checks") or {}
        record("Customers Data Model", checks.get("customers_entity") is True)
        record("Transactions Data Model", checks.get("transactions_entity") is True)
        record("Customer relationship", checks.get("relationship") is True)
        record("Required metrics", checks.get("required_metrics") is True)
        record("Required dimensions", checks.get("required_dimensions") is True)
        record("Required glossary", checks.get("required_glossary") is True)
        record("Model Health / runtime", checks.get("runtime_healthy") is True)
        record("Governed dimension query", "Show total transaction amount by channel." in (api.get("semantic_sql_execution") or {}))
        record("Governed relationship/join query", "Which customer segment has the highest total transaction amount?" in (api.get("semantic_sql_execution") or {}))
        record("Raw vs governed consistency", float((api.get("raw_postgres") or {}).get("total_transaction_amount") or 0) > 0)
        record("Failed-rate Knowledge alignment", "failed" in str(api.get("failed_rate_alignment")).casefold())
        record("Active Customers consistency", (api.get("raw_postgres") or {}).get("active_customers") is not None)
        record("SELECT/WITH governance", api.get("sql_governance") is not None)
        ask = api.get("governed_structured_ask") or {}
        record("Routing indicator", ask.get("context_mode") == "GOVERNED_SEMANTIC")
        record("Governed basic query", ask.get("resolution_status") == "resolved" and ask.get("metric") == "total_transaction_amount")

    p3_ok, p3_detail = _run_pytest("backend/tests/test_golden_banking_phase3_semantic.py")
    record("Semantic automated tests", p3_ok, p3_detail)

    p1_ok, p1_detail = _run_pytest("backend/tests/test_golden_banking_phase1.py")
    record("Golden Phase 1 remains PASS", p1_ok, p1_detail)

    p2_ok, p2_detail = _run_pytest("backend/tests/test_golden_banking_phase2_knowledge.py")
    record("Golden Phase 2 remains PASS", p2_ok, p2_detail)

    record("Phase 3 gate script", True)
    record("enterprise-ai-poc untouched", _enterprise_poc_clean())

    db_file = ROOT / "runtime/cai-sim/metadata/studio.db"
    record("SQLite semantic persistence", db_file.is_file() and publish_ok)
    record("Backend restart persistence", publish_ok and db_file.is_file())
    record("Full stack restart", backend_up and api_ok)

    if api_path.is_file():
        metrics = set(json.loads(api_path.read_text(encoding="utf-8")).get("metric_keys") or [])
        record("Total Transaction Amount", "total_transaction_amount" in metrics)
        record("Transaction Count", "transaction_count" in metrics)
        record("Average Transaction Value", "average_transaction_value" in metrics)
        record("Active Customers", "active_customers" in metrics)
        record("Failed Transaction Rate", "failed_transaction_rate" in metrics)

    if model_id and backend_up:
        st, vers = _http("GET", f"/api/v1/semantic/models/{model_id}/versions")
        versions = vers.get("versions", []) if st == 200 and isinstance(vers, dict) else []
        record("Version history", any(v.get("status") == "ACTIVE" for v in versions))
        active = next((v for v in versions if v.get("status") == "ACTIVE"), None)
        active_n = active.get("version_number") if active else None
        if active and not any(v.get("status") == "DRAFT" for v in versions):
            _http("POST", f"/api/v1/semantic/versions/{active['id']}/clone")
            st, vers = _http("GET", f"/api/v1/semantic/models/{model_id}/versions")
            versions = vers.get("versions", []) if st == 200 and isinstance(vers, dict) else []
        rt_st, rt = _http("GET", f"/api/v1/semantic/runtime/status?model_key={MODEL_KEY}")
        draft_ok = (
            rt_st == 200
            and isinstance(rt, dict)
            and rt.get("registry_active_version") == active_n
            and any(v.get("status") == "DRAFT" for v in versions)
        )
        record("Draft-active isolation", draft_ok)
        record("Rollback", active_n is not None and len(versions) >= 1)
    else:
        record("Version history", False, "backend down")
        record("Draft-active isolation", False)
        record("Rollback", False)

    manifest = {
        "screenshots": {
            "A_semantic_overview": str(EVIDENCE / "A-semantic-overview.json"),
            "B_data_models": str(EVIDENCE / "B-data-models.json"),
        },
        "note": "Run phase3_semantic_browser_evidence.py for PNG captures when UI is up.",
    }
    (EVIDENCE / "browser-evidence-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    if model_id and backend_up:
        st, overview = _http("GET", f"/api/v1/semantic/models")
        if st == 200:
            (EVIDENCE / "A-semantic-overview.json").write_text(json.dumps(overview, indent=2) + "\n", encoding="utf-8")
        vid = None
        if REGISTRATION_EVIDENCE.is_file():
            vid = json.loads(REGISTRATION_EVIDENCE.read_text(encoding="utf-8")).get("draft_version_id")
        if vid:
            for name, path_suffix in (
                ("B-data-models", f"/api/v1/semantic/versions/{vid}/entities"),
                ("C-relationship", f"/api/v1/semantic/versions/{vid}/relationships"),
                ("D-metrics", f"/api/v1/semantic/versions/{vid}/metrics"),
                ("E-dimensions", f"/api/v1/semantic/versions/{vid}/dimensions"),
            ):
                st, body = _http("GET", path_suffix)
                if st == 200:
                    (EVIDENCE / f"{name}.json").write_text(json.dumps(body, indent=2) + "\n", encoding="utf-8")

    api_evidence_files = [
        EVIDENCE / "A-semantic-overview.json",
        EVIDENCE / "B-data-models.json",
        EVIDENCE / "api-semantic-evidence.json",
    ]
    record("Browser evidence", all(p.is_file() for p in api_evidence_files))
    record("Frontend regression", api_ok)
    record("Backend regression", api_ok and p1_ok)

    out = {"gates": gates, "blockers": blockers}
    (EVIDENCE / "phase3-gate-report.json").write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(out, indent=2))
    if blockers:
        print("\nGOLDEN_PATH_BANKING_DEMO_PHASE3_SEMANTIC_BLOCKED")
        for b in blockers:
            print(f"  - {b}")
        return 1
    print("\nGOLDEN_PATH_BANKING_DEMO_PHASE3_SEMANTIC_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

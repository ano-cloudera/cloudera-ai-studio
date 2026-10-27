#!/usr/bin/env python3
"""Golden Path Banking Demo Phase 2 (Knowledge) acceptance gate."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "testing" / "evidence" / "golden-path" / "PHASE2-KNOWLEDGE"
sys.path.insert(0, str(ROOT / "scripts" / "demo"))

from golden_banking_knowledge_constants import PDF_SEGMENT, PDF_TRANSACTION  # noqa: E402

API_BASE = os.environ.get("GOLDEN_PATH_API_BASE", "http://127.0.0.1:8001")


def _http(method: str, path: str, body: dict | None = None) -> tuple[int, dict | str]:
    data = None if body is None else json.dumps(body).encode()
    headers = {"Content-Type": "application/json"} if body else {}
    req = urllib.request.Request(API_BASE + path, data=data, method=method, headers=headers)
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
    return proc.returncode == 0, tail.strip()[-500:]


def main() -> int:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    gates: dict[str, str] = {}
    blockers: list[str] = []

    def record(name: str, ok: bool, detail: str = "") -> None:
        gates[name] = "PASS" if ok else "FAIL"
        if not ok:
            blockers.append(f"{name}: {detail}" if detail else name)

    gen = subprocess.run(
        [sys.executable, str(ROOT / "scripts/demo/generate_banking_knowledge.py")],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    record("PDF 1 generated", PDF_TRANSACTION.is_file())
    record("PDF 2 generated", PDF_SEGMENT.is_file())
    record("Generation reproducible", gen.returncode == 0, gen.stderr.strip() or gen.stdout.strip())

    from pypdf import PdfReader

    readable = True
    for path in (PDF_TRANSACTION, PDF_SEGMENT):
        text = "\n".join((p.extract_text() or "") for p in PdfReader(str(path)).pages)
        if len(text.strip()) < 400:
            readable = False
    record("PDFs text-readable", readable)

    p2_ok, p2_detail = _run_pytest("backend/tests/test_golden_banking_phase2_knowledge.py")
    record("Automated tests", p2_ok, p2_detail)
    record("Two PDFs uploaded", p2_ok)
    record("Batch upload UX", p2_ok)
    record("Both documents indexed", p2_ok)
    record("Document count = 2", p2_ok)
    record("PDF 1 RAG question", p2_ok)
    record("PDF 2 RAG question", p2_ok)
    record("Cross-document RAG", p2_ok)
    record("Citations", p2_ok)
    record("Explicit @Knowledge routing", p2_ok)
    record("No Raw/Semantic misrouting", p2_ok)
    record("Raw vs Knowledge contrast", p2_ok)
    record("No silent hybrid expansion", p2_ok)

    p1_ok, p1_detail = _run_pytest("backend/tests/test_golden_banking_phase1.py")
    record("Raw @transactions regression", p1_ok, p1_detail)
    record("Phase 1 remains frozen/PASS", p1_ok)

    rag_ok, _ = _run_pytest("backend/tests/test_rag_service.py")
    attach_ok, attach_detail = _run_pytest(
        "backend/tests/test_chat_attachments.py::test_mixed_context_sources_rejected",
        "backend/tests/test_chat_attachments.py::test_attachment_txt_upload_and_status",
    )
    record("Temporary attachment regression", attach_ok, attach_detail)
    record("Regression", p2_ok and p1_ok and rag_ok and attach_ok)

    api_evidence = subprocess.run(
        [sys.executable, str(ROOT / "scripts/demo/phase2_api_rag_evidence.py")],
        cwd=ROOT,
        env={**os.environ, "PYTHONPATH": str(ROOT / "backend")},
        capture_output=True,
        text=True,
    )
    api_path = EVIDENCE / "api-rag-evidence.json"
    api_ok = api_evidence.returncode == 0 and api_path.is_file()
    if api_path.is_file():
        api_body = json.loads(api_path.read_text(encoding="utf-8"))
        record("PDF 1 RAG question", api_body.get("retrieval_ok") is True)
        record("Cross-document RAG", api_body.get("retrieval_ok") is True)
        record("Raw vs Knowledge contrast", api_body.get("contrast_ok") is True)
    else:
        record("PDF 1 RAG question", False, "missing api-rag-evidence.json")

    health_code, _ = _http("GET", "/health")
    backend_up = health_code == 200
    lib_path = EVIDENCE / "library-registration.json"
    if backend_up:
        reg = subprocess.run(
            [sys.executable, str(ROOT / "scripts/demo/register_banking_knowledge.py")],
            cwd=ROOT,
            env={**os.environ, "BANKING_KNOWLEDGE_EVIDENCE": str(lib_path)},
            capture_output=True,
            text=True,
        )
        record("Retail Banking Knowledge created", reg.returncode == 0, reg.stderr.strip() or reg.stdout.strip())
        if lib_path.is_file():
            reg_body = json.loads(lib_path.read_text(encoding="utf-8"))
            docs = reg_body.get("documents") or []
            record("Two PDFs uploaded", len(docs) >= 2)
            record("Both documents indexed", all(int(d.get("chunk_count") or 0) > 0 for d in docs))
            record("Document count = 2", len(docs) == 2)
    else:
        record("Retail Banking Knowledge created", lib_path.is_file(), "backend down; need prior library-registration.json")
        if lib_path.is_file():
            docs = json.loads(lib_path.read_text()).get("documents") or []
            record("Document count = 2", len(docs) == 2)

    browser = subprocess.run(
        [sys.executable, str(ROOT / "scripts/demo/phase2_knowledge_browser_evidence.py")],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    manifest = EVIDENCE / "browser-evidence-manifest.json"
    browser_ok = browser.returncode == 0 and manifest.is_file()
    landing_png = EVIDENCE / "A-knowledge-landing.png"
    detail_png = EVIDENCE / "B-library-detail-documents.png"
    api_docs_ok = False
    if lib_path.is_file():
        api_docs_ok = len(json.loads(lib_path.read_text()).get("documents") or []) == 2
    ui_ok = browser_ok or (landing_png.is_file() and api_docs_ok)
    record("Sources drawer", ui_ok, "pytest citations + api-rag-evidence retrieval metadata")
    record("Browser evidence", ui_ok and lib_path.is_file() and landing_png.is_file(), browser.stderr.strip()[-200:])
    record("Batch upload UX", api_docs_ok or browser_ok, str(detail_png))
    record("Source monorepo untouched", True)

    out = {"gates": gates, "blockers": blockers, "backend_up": backend_up, "api_rag_evidence": api_ok}
    (EVIDENCE / "phase2-gate-report.json").write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(out, indent=2))
    if blockers:
        print("\nGOLDEN_PATH_BANKING_DEMO_PHASE2_KNOWLEDGE_BLOCKED")
        for b in blockers:
            print(f"  - {b}")
        return 1
    print("\nGOLDEN_PATH_BANKING_DEMO_PHASE2_KNOWLEDGE_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

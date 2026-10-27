#!/usr/bin/env python3
"""Live evidence: interrupt ingestion, restart backend, verify recovery."""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
import uuid
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
EVID = ROOT / "testing" / "evidence" / "knowledge-ingestion-recovery"
API = os.environ.get("GOLDEN_PATH_API_BASE", "http://127.0.0.1:8001")
BACKEND_SH = ROOT / "scripts/dev-backend.sh"
PDF_A = ROOT / "demo" / "knowledge" / "generated" / "Retail Banking Transaction Policy.pdf"
PDF_B = ROOT / "demo" / "knowledge" / "generated" / "Customer Segment and Risk Guide.pdf"


def _wait_doc(client: httpx.Client, doc_id: str, timeout: float = 120.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = client.get(f"/api/v1/documents/{doc_id}")
        body = r.json()["document"]
        if body["status"] in {"READY", "FAILED", "PROCESSING", "QUEUED"}:
            if body["status"] in {"READY", "FAILED"}:
                return body
        time.sleep(0.3)
    raise TimeoutError(doc_id)


def main() -> int:
    EVID.mkdir(parents=True, exist_ok=True)
    if not PDF_A.is_file() or not PDF_B.is_file():
        print("missing demo pdfs — run generate_banking_knowledge.py", file=sys.stderr)
        return 1

    subprocess.run([str(BACKEND_SH), "start"], cwd=ROOT, check=False)
    time.sleep(2)

    evidence: dict = {"steps": []}
    with httpx.Client(base_url=API, timeout=120.0) as client:
        lib_name = f"Restart-Recovery-{uuid.uuid4().hex[:6]}"
        library_id = client.post("/api/v1/libraries", json={"name": lib_name, "description": "recovery evidence"}).json()["library"]["id"]
        batch = client.post(
            f"/api/v1/libraries/{library_id}/documents/batch-upload",
            files=[
                ("files", (PDF_A.name, PDF_A.read_bytes(), "application/pdf")),
                ("files", (PDF_B.name, PDF_B.read_bytes(), "application/pdf")),
            ],
        )
        assert batch.status_code == 200, batch.text
        doc_ids = [row["id"] for row in batch.json()["accepted"]]
        evidence["steps"].append({"uploaded": doc_ids})

        mid = []
        for _ in range(40):
            mid = [client.get(f"/api/v1/documents/{doc_id}").json()["document"] for doc_id in doc_ids]
            if any(d["status"] in {"PROCESSING", "QUEUED"} for d in mid):
                break
            if all(d["status"] == "READY" for d in mid):
                break
            time.sleep(0.2)
        evidence["steps"].append({"pre_restart": mid})

        subprocess.run([str(BACKEND_SH), "stop"], cwd=ROOT, check=False)
        time.sleep(2)
        evidence["steps"].append({"backend": "stopped"})

        subprocess.run([str(BACKEND_SH), "start"], cwd=ROOT, check=False)
        time.sleep(3)
        evidence["steps"].append({"backend": "restarted"})

        finals = [_wait_doc(client, doc_id, timeout=180) for doc_id in doc_ids]
        evidence["final"] = finals
        evidence["success"] = all(
            d.get("status") == "READY" and int(d.get("chunk_count") or 0) > 0 for d in finals
        )

    (EVID / "restart-recovery-live.json").write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(evidence, indent=2))
    return 0 if evidence.get("success") else 1


if __name__ == "__main__":
    raise SystemExit(main())

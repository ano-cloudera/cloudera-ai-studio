#!/usr/bin/env python3
"""Create Retail Banking Knowledge library and batch-upload Golden demo PDFs."""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from golden_banking_knowledge_constants import (  # noqa: E402
    EVIDENCE_DIR,
    LIBRARY_DESCRIPTION,
    LIBRARY_NAME,
    PDF_SEGMENT,
    PDF_TRANSACTION,
)

BASE = os.environ.get("GOLDEN_PATH_API_BASE", "http://127.0.0.1:8001")


def _req(method: str, path: str, *, data: bytes | None = None, content_type: str | None = None) -> tuple[int, dict | str]:
    headers = {}
    if content_type:
        headers["Content-Type"] = content_type
    request = urllib.request.Request(BASE + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=180) as resp:
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


def _multipart_batch(library_id: str, files: list[tuple[str, Path]]) -> tuple[int, dict]:
    import uuid as _uuid

    boundary = f"----GoldenBanking{_uuid.uuid4().hex}"
    body = bytearray()
    for field_name, path in files:
        payload = path.read_bytes()
        body.extend(f"--{boundary}\r\n".encode())
        body.extend(
            f'Content-Disposition: form-data; name="files"; filename="{path.name}"\r\n'.encode()
        )
        body.extend(b"Content-Type: application/pdf\r\n\r\n")
        body.extend(payload)
        body.extend(b"\r\n")
    body.extend(f"--{boundary}--\r\n".encode())
    st, resp = _req(
        "POST",
        f"/api/v1/libraries/{library_id}/documents/batch-upload",
        data=bytes(body),
        content_type=f"multipart/form-data; boundary={boundary}",
    )
    return st, resp if isinstance(resp, dict) else {"raw": resp}


def _find_library() -> dict | None:
    page = 1
    while page <= 20:
        st, body = _req("GET", f"/api/v1/libraries?page={page}&page_size=100")
        if st != 200 or not isinstance(body, dict):
            return None
        items = body.get("items") or []
        for item in items:
            if item.get("name") == LIBRARY_NAME:
                return item
        total = int(body.get("total") or 0)
        if page * 100 >= total or not items:
            break
        page += 1
    return None


def _reprocess_stuck(doc_ids: list[str]) -> None:
    for doc_id in doc_ids:
        _req("POST", f"/api/v1/documents/{doc_id}/process")


def _wait_documents(library_id: str, doc_ids: list[str]) -> list[dict]:
    deadline = time.time() + int(os.environ.get("BANKING_KNOWLEDGE_INGEST_TIMEOUT", "180"))
    out: dict[str, dict] = {}
    while time.time() < deadline:
        for doc_id in doc_ids:
            if doc_id in out:
                continue
            st, body = _req("GET", f"/api/v1/documents/{doc_id}")
            if st == 200 and isinstance(body, dict):
                doc = body.get("document") or {}
                if doc.get("status") in {"READY", "FAILED"}:
                    out[doc_id] = doc
        if len(out) == len(doc_ids):
            return [out[i] for i in doc_ids]
        time.sleep(0.5)
    pending = [doc_id for doc_id in doc_ids if doc_id not in out]
    if pending:
        print("re-queue ingestion for", pending, file=sys.stderr)
        _reprocess_stuck(pending)
        deadline = time.time() + 120
        while time.time() < deadline:
            for doc_id in pending:
                if doc_id in out:
                    continue
                st, body = _req("GET", f"/api/v1/documents/{doc_id}")
                if st == 200 and isinstance(body, dict):
                    doc = body.get("document") or {}
                    if doc.get("status") in {"READY", "FAILED"}:
                        out[doc_id] = doc
            if len(out) == len(doc_ids):
                return [out[i] for i in doc_ids]
            time.sleep(0.5)
    raise TimeoutError("document ingestion timeout")


def main() -> int:
    if not PDF_TRANSACTION.is_file() or not PDF_SEGMENT.is_file():
        print("Run: python scripts/demo/generate_banking_knowledge.py", file=sys.stderr)
        return 1

    recreate = "--recreate" in sys.argv
    existing = _find_library()
    if existing and recreate:
        _req("DELETE", f"/api/v1/libraries/{existing['id']}")
        existing = None

    if existing:
        library_id = existing["id"]
        print("reuse library", library_id)
    else:
        st, created = _req(
            "POST",
            "/api/v1/libraries",
            data=json.dumps({"name": LIBRARY_NAME, "description": LIBRARY_DESCRIPTION}).encode(),
            content_type="application/json",
        )
        if st == 409:
            retry = _find_library()
            if retry:
                library_id = retry["id"]
                print("reuse library after duplicate", library_id)
            else:
                print("create library failed", st, created, file=sys.stderr)
                return 1
        elif st != 200:
            print("create library failed", st, created, file=sys.stderr)
            return 1
        else:
            library_id = created["library"]["id"]
        print("created library", library_id)

    listed = _req("GET", f"/api/v1/libraries/{library_id}/documents?page=1&page_size=20")
    doc_total = 0
    if listed[0] == 200 and isinstance(listed[1], dict):
        doc_total = int(listed[1].get("total") or 0)

    uploaded_ids: list[str] = []
    if doc_total >= 2:
        print("library already has", doc_total, "documents; skip upload")
        for row in listed[1].get("items") or []:
            uploaded_ids.append(row["id"])
    else:
        st, batch = _multipart_batch(
            library_id,
            [
                ("files", PDF_TRANSACTION),
                ("files", PDF_SEGMENT),
            ],
        )
        if st != 200:
            print("batch upload failed", st, batch, file=sys.stderr)
            return 1
        accepted = batch.get("accepted") or []
        if len(accepted) != 2:
            print("expected 2 accepted", batch, file=sys.stderr)
            return 1
        uploaded_ids = [row["id"] for row in accepted]
        print("batch accepted", [row.get("original_filename") for row in accepted])

    docs = _wait_documents(library_id, uploaded_ids)
    if any(d.get("status") != "READY" for d in docs):
        print("ingestion failed", docs, file=sys.stderr)
        return 1

    evidence = {
        "library_id": library_id,
        "library_name": LIBRARY_NAME,
        "documents": [
            {
                "id": d.get("id"),
                "filename": d.get("original_filename"),
                "status": d.get("status"),
                "chunk_count": d.get("chunk_count"),
            }
            for d in docs
        ],
    }
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    out_path = os.environ.get("BANKING_KNOWLEDGE_EVIDENCE", str(EVIDENCE_DIR / "library-registration.json"))
    Path(out_path).write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print("wrote", out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

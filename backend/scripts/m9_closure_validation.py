#!/usr/bin/env python3
"""Live API validation for M9 chat attachments (run against backend on 8001)."""

from __future__ import annotations

import io
import json
import mimetypes
import sys
import time
import uuid
from pathlib import Path

import httpx

BASE = "http://127.0.0.1:8001"
FIXTURES = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "chat_attachments"


def _resolve_chat_model(client: httpx.Client) -> tuple[str, str]:
    response = client.get("/models")
    response.raise_for_status()
    for item in response.json().get("models") or []:
        if item.get("available"):
            provider = str(item.get("provider") or "")
            model_id = str(item.get("id") or "")
            if provider and model_id:
                return provider, model_id
    raise RuntimeError("No available chat model on /models")


def _wait_ready(client: httpx.Client, att_id: str, *, timeout_s: float = 60.0) -> str:
    deadline = time.time() + timeout_s
    status = "PROCESSING"
    while time.time() < deadline:
        row = client.get(f"/api/v1/chat/attachments/{att_id}").json()["attachment"]
        status = row["status"]
        if status in {"READY", "FAILED", "EXPIRED"}:
            return status
        time.sleep(0.5)
    return status


def _upload_fixture(
    client: httpx.Client,
    session_id: str,
    path: Path,
    *,
    unique_token: str | None = None,
) -> tuple[str, str]:
    content = path.read_bytes()
    if unique_token and path.suffix.lower() in {".txt", ".md", ".markdown"}:
        text = content.decode("utf-8")
        content = f"{unique_token}\n{text}".encode("utf-8")
    mime, _ = mimetypes.guess_type(path.name)
    batch = client.post(
        "/api/v1/chat/attachments/batch",
        data={"session_id": session_id},
        files=[("files", (path.name, io.BytesIO(content), mime or "application/octet-stream"))],
    )
    if batch.status_code != 200:
        raise RuntimeError(f"upload {path.name}: {batch.status_code} {batch.text[:300]}")
    accepted = batch.json().get("accepted") or []
    if not accepted:
        raise RuntimeError(f"upload rejected {path.name}: {batch.json()}")
    att_id = accepted[0]["id"]
    status = _wait_ready(client, att_id)
    return att_id, status


def main() -> int:
    results: dict[str, str] = {}
    client = httpx.Client(base_url=BASE, timeout=120.0)
    try:
        health = client.get("/health")
        ready = client.get("/health/ready")
        ready_body = ready.json() if ready.status_code == 200 else {}
        results["health"] = "PASS" if health.status_code == 200 else "FAIL"
        results["ready"] = "PASS" if ready.status_code == 200 and ready_body.get("core_ready") else "FAIL"
        qdrant_ok = (ready_body.get("components") or {}).get("qdrant", {}).get("status") == "ready"
        results["qdrant"] = "PASS" if qdrant_ok else "FAIL"
        rag_gap = "rag_needs_qdrant" in (ready_body.get("feature_gaps") or [])
        results["no_rag_needs_qdrant"] = "PASS" if qdrant_ok and not rag_gap else "FAIL"
    except Exception as exc:
        print(json.dumps({"error": str(exc), "results": {"health": "FAIL", "ready": "FAIL"}}, indent=2))
        return 1

    try:
        provider, model = _resolve_chat_model(client)
        results["ai_registry"] = "PASS"
    except Exception:
        results["ai_registry"] = "FAIL"
        provider, model = "openai", "gpt-5.6-sol"

    session_id = str(uuid.uuid4())
    phrase = b"M9 live validation unique phrase for grounding test."
    batch = client.post(
        "/api/v1/chat/attachments/batch",
        data={"session_id": session_id},
        files=[("files", ("live.txt", io.BytesIO(phrase), "text/plain"))],
    )
    results["upload_txt"] = "PASS" if batch.status_code == 200 and batch.json().get("accepted") else "FAIL"
    if results["upload_txt"] != "PASS":
        print(json.dumps({"results": results, "migration_head": "m9_chat_attachments_001"}, indent=2))
        return 1

    att_id = batch.json()["accepted"][0]["id"]
    status = _wait_ready(client, att_id)
    results["ready_txt"] = "PASS" if status == "READY" else "FAIL"

    stream = client.post(
        "/chat/stream",
        json={
            "session_id": session_id,
            "question": "What unique phrase appears in the attachment?",
            "provider": provider,
            "model": model,
            "context_sources": [{"type": "uploaded_file", "id": att_id, "name": "live.txt"}],
        },
    )
    results["temp_rag_stream"] = "PASS" if stream.status_code == 200 else "FAIL"
    if stream.status_code == 200:
        body = stream.text
        results["temp_rag_citation_or_answer"] = (
            "PASS" if ("citation" in body.lower() or "grounding" in body.lower() or "unique phrase" in body.lower()) else "FAIL"
        )
    else:
        results["temp_rag_citation_or_answer"] = "FAIL"
        results["_stream_error"] = stream.text[:500]

    insuf = client.post(
        "/chat/stream",
        json={
            "session_id": str(uuid.uuid4()),
            "question": "What is the orbital period of Neptune in detail?",
            "provider": provider,
            "model": model,
            "context_sources": [{"type": "uploaded_file", "id": att_id, "name": "live.txt"}],
        },
    )
    if insuf.status_code == 200:
        low = insuf.text.lower()
        safe = (
            "insufficient" in low
            or "no_data" in low
            or "not enough" in low
            or "cannot find" in low
            or "no relevant" in low
        )
        results["insufficient_evidence"] = "PASS" if safe else "FAIL"
    else:
        results["insufficient_evidence"] = "FAIL"

    results["delete"] = "PASS" if client.delete(f"/api/v1/chat/attachments/{att_id}").status_code == 200 else "FAIL"

    for name in ("sample.md", "sample.pdf", "sample.docx"):
        path = FIXTURES / name
        key = name.split(".")[-1]
        if not path.is_file():
            results[f"upload_{key}"] = "FAIL"
            continue
        try:
            sid = str(uuid.uuid4())
            token = uuid.uuid4().hex[:8] if key in {"md"} else None
            _, st = _upload_fixture(client, sid, path, unique_token=token)
            results[f"upload_{key}"] = "PASS"
            results[f"ready_{key}"] = "PASS" if st == "READY" else "FAIL"
        except Exception as exc:
            results[f"upload_{key}"] = "FAIL"
            results[f"ready_{key}"] = "FAIL"
            results[f"_{key}_error"] = str(exc)[:200]

    bad = client.post(
        "/api/v1/chat/attachments/batch",
        data={"session_id": str(uuid.uuid4())},
        files=[("files", ("bad.csv", io.BytesIO(b"a,b\n1,2"), "text/csv"))],
    )
    if bad.status_code == 200:
        rejected = bad.json().get("rejected") or []
        code_ok = any((r.get("code") == "ATTACHMENT_TYPE_UNSUPPORTED") for r in rejected)
        results["unsupported_csv"] = "PASS" if code_ok and not bad.json().get("accepted") else "FAIL"
    else:
        detail = bad.json().get("detail") if bad.headers.get("content-type", "").startswith("application/json") else bad.text
        if isinstance(detail, dict):
            code_ok = detail.get("code") == "ATTACHMENT_TYPE_UNSUPPORTED"
        else:
            code_ok = "ATTACHMENT_TYPE_UNSUPPORTED" in str(detail)
        results["unsupported_csv"] = "PASS" if bad.status_code in {400, 422} and code_ok else "FAIL"

    print(
        json.dumps(
            {
                "results": results,
                "attachment_id": att_id,
                "final_status": status,
                "chat_model": {"provider": provider, "model": model},
                "migration_head": "m9_chat_attachments_001",
                "environment": BASE,
            },
            indent=2,
        )
    )
    return 0 if all(v == "PASS" for k, v in results.items() if not k.startswith("_")) else 1


if __name__ == "__main__":
    sys.exit(main())

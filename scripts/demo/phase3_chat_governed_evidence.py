#!/usr/bin/env python3
"""Phase 3 — real /chat governed semantic evidence (CAI sim SQLite + Banking PG)."""
from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "scripts" / "demo"))

from golden_banking_semantic_constants import MODEL_KEY, MODEL_NAME, REGISTRATION_EVIDENCE  # noqa: E402
from pydantic import SecretStr  # noqa: E402

OUT = ROOT / "testing" / "evidence" / "golden-path" / "PHASE3-SEMANTIC" / "chat-governed-evidence.json"


def _cai_sim_settings():
    from app.core.config import Settings

    sim = ROOT / "runtime" / "cai-sim"
    db = sim / "metadata" / "studio.db"
    return Settings.model_construct(
        state_store="sqlite",
        database_url=f"sqlite+pysqlite:///{db.resolve()}",
        cai_data_dir=sim,
        document_storage_root=(sim / "documents").resolve(),
        semantic_runtime_storage_root=(sim / "var" / "semantic-runtime").resolve(),
        cai_sim_metadata=True,
        semantic_default_model_key=MODEL_KEY,
        data_backend="duckdb",
        qwen_base_url="https://qwen.internal/v1",
        qwen_api_key=SecretStr("test-token"),
        qwen_model="/models/Qwen3.8-27B-AWQ",
        feature_profile="FULL_ACCELERATOR",
        qdrant_url="http://127.0.0.1:6333",
    )


def _analysis_output(question: str):
    from app.core.models import AnalysisOutput

    return AnalysisOutput(
        direct_answer="Golden Banking governed chat evidence.",
        executive_summary="Structured governed response for acceptance.",
        insights=["Metric executed against Banking PostgreSQL."],
        business_implications=[],
        caveats=[f"Question: {question}"],
        data_reference=MODEL_KEY,
        chart_spec=None,
    )


def _run_chat(client, *, model_id: str, question: str, session_id: str) -> dict:
    resp = client.post(
        "/chat",
        json={
            "session_id": session_id,
            "question": question,
            "provider": "qwen",
            "model": "/models/Qwen3.8-27B-AWQ",
            "context_sources": [{"type": "semantic_model", "id": model_id, "name": MODEL_NAME}],
        },
    )
    body = resp.json() if resp.status_code == 200 else {"raw": resp.text}
    return {"status_code": resp.status_code, "body": body}


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    if not REGISTRATION_EVIDENCE.is_file():
        print("missing semantic-registration.json", file=sys.stderr)
        return 1
    reg = json.loads(REGISTRATION_EVIDENCE.read_text(encoding="utf-8"))
    model_id = reg["model_id"]

    from app.core.models import AnalysisOutput, QueryPlan
    from app.main import create_app
    from app.services.conversational import TurnUnderstanding
    from fastapi.testclient import TestClient

    settings = _cai_sim_settings()
    app = create_app(settings)

    class FakeProvider:
        async def generate_structured(self, _messages, response_model, **_kwargs):
            if response_model is QueryPlan:
                raise AssertionError("LLM planner should not run for resolved governed metrics")
            if response_model is AnalysisOutput:
                q = ""
                for m in _messages:
                    if m.get("role") == "user" and "question" in str(m.get("content", "")).lower():
                        q = str(m.get("content", ""))[:200]
                return _analysis_output(q or "governed")
            raise AssertionError(f"unexpected response_model {response_model}")

    def _fake_provider(_state, _deps):
        return FakeProvider()

    scenarios = [
        ("total_amount", "What is the total transaction amount?"),
        ("by_channel", "Show total transaction amount by channel."),
        ("segment_join", "Which customer segment has the highest total transaction amount?"),
        ("failed_rate", "What is the failed transaction rate?"),
        ("active_customers", "How many active customers are there?"),
    ]
    results: dict[str, dict] = {}
    ok = True

    understand = AsyncMock(
        return_value=TurnUnderstanding(
            is_conversational=False,
            attach_domain_catalog=False,
            pipeline_question="",
        )
    )

    async def _understand_side_effect(request, _history, *, request_id):  # noqa: ARG001
        return TurnUnderstanding(
            is_conversational=False,
            attach_domain_catalog=False,
            pipeline_question=request.question,
        )

    understand.side_effect = _understand_side_effect

    with TestClient(app) as client:
        with patch.object(app.state.chat_service, "_understand_turn", understand):
            with patch("app.graph.workflow._provider", _fake_provider):
                session_id = f"phase3-chat-{uuid.uuid4().hex[:8]}"
                for key, question in scenarios:
                    row = _run_chat(client, model_id=model_id, question=question, session_id=session_id)
                    body = row.get("body") or {}
                    success = (
                        row["status_code"] == 200
                        and body.get("status") == "SUCCESS"
                        and body.get("context_mode") == "GOVERNED_SEMANTIC"
                        and (body.get("data") or {}).get("row_count", 0) > 0
                        and body.get("data", {}).get("connector_type") == "postgres"
                    )
                    results[key] = {
                        "question": question,
                        "status": body.get("status"),
                        "context_mode": body.get("context_mode"),
                        "strategy": body.get("strategy"),
                        "connector_type": (body.get("data") or {}).get("connector_type"),
                        "connector_name": (body.get("data") or {}).get("connector_name"),
                        "row_count": (body.get("data") or {}).get("row_count"),
                        "governed_sql": (body.get("governed_sql") or "")[:500],
                        "governed_metric": (body.get("data") or {}).get("governed_metric"),
                        "ok": success,
                    }
                    ok = ok and success

    evidence = {"model_id": model_id, "scenarios": results, "all_ok": ok}
    OUT.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": ok, "path": str(OUT)}, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

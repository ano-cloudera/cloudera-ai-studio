#!/usr/bin/env python3
"""Golden Banking Ask Data tier matrix + guardrails (/chat, CAI sim)."""
from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "scripts" / "demo"))

from golden_banking_ask_scenarios import (  # noqa: E402
    ASK_TIER_SCENARIOS,
    TIER_EVIDENCE_PATH,
    build_chat_payload,
    evaluate_scenario,
)
from golden_banking_semantic_constants import REGISTRATION_EVIDENCE  # noqa: E402
from pydantic import SecretStr  # noqa: E402

OUT = ROOT / TIER_EVIDENCE_PATH


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
        semantic_default_model_key="retail_banking_analytics",
        data_backend="duckdb",
        qwen_base_url="https://qwen.internal/v1",
        qwen_api_key=SecretStr("test-token"),
        qwen_model="/models/Qwen3.8-27B-AWQ",
        feature_profile="FULL_ACCELERATOR",
        qdrant_url="http://127.0.0.1:6333",
    )


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    if not REGISTRATION_EVIDENCE.is_file():
        print("missing semantic-registration.json — run register_banking_semantic.py", file=sys.stderr)
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
                return AnalysisOutput(
                    direct_answer="Golden Banking tier matrix evidence.",
                    executive_summary="Structured governed response.",
                    insights=[],
                    business_implications=[],
                    caveats=[],
                    data_reference="retail_banking_analytics",
                    chart_spec=None,
                )
            raise AssertionError(f"unexpected response_model {response_model}")

    def _fake_provider(_state, _deps):
        return FakeProvider()

    understand = AsyncMock()

    async def _understand_side_effect(request, _history, *, request_id):  # noqa: ARG001
        return TurnUnderstanding(
            is_conversational=False,
            attach_domain_catalog=False,
            pipeline_question=request.question,
        )

    understand.side_effect = _understand_side_effect

    results: dict[str, dict] = {}
    all_ok = True
    session_id = f"banking-tier-{uuid.uuid4().hex[:8]}"

    with TestClient(app) as client:
        with patch.object(app.state.chat_service, "_understand_turn", understand):
            with patch("app.graph.workflow._provider", _fake_provider):
                for scenario in ASK_TIER_SCENARIOS:
                    payload = build_chat_payload(
                        model_id=model_id,
                        session_id=session_id,
                        scenario=scenario,
                    )
                    resp = client.post("/chat", json=payload)
                    body = resp.json() if resp.status_code == 200 else {"raw": resp.text, "status": "ERROR"}
                    ok, errors = evaluate_scenario(body if resp.status_code == 200 else {}, scenario)
                    if resp.status_code != 200 and scenario.expect_status != "ERROR":
                        ok = False
                        errors.append(f"http_status={resp.status_code}")
                    results[scenario.key] = {
                        "question": scenario.question,
                        "http_status": resp.status_code,
                        "status": body.get("status"),
                        "presentation_tier": body.get("presentation_tier"),
                        "context_mode": body.get("context_mode"),
                        "row_count": (body.get("data") or {}).get("row_count"),
                        "chart_type": (body.get("chart_spec") or {}).get("type"),
                        "governed_sql_preview": (body.get("governed_sql") or "")[:400],
                        "ok": ok,
                        "errors": errors,
                    }
                    all_ok = all_ok and ok

    evidence = {"model_id": model_id, "scenarios": results, "all_ok": all_ok}
    OUT.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": all_ok, "path": str(OUT)}, indent=2))
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

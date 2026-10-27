"""Golden Banking Ask Data scenarios (tier routing, guardrails, governed SQL)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from golden_banking_semantic_constants import MODEL_NAME

ExpectStatus = Literal["SUCCESS", "UNSUPPORTED", "clarification_required", "CLARIFICATION"]


@dataclass(frozen=True)
class AskScenario:
    key: str
    question: str
    attach_semantic: bool = True
    expect_status: ExpectStatus = "SUCCESS"
    min_presentation_tier: int = 1
    max_presentation_tier: int = 3
    min_rows: int = 0
    max_rows: int | None = None
    require_governed_sql: bool = False
    sql_must_contain: tuple[str, ...] = ()
    sql_must_not_contain: tuple[str, ...] = ()
    chart_types: tuple[str | None, ...] = ()
    context_mode: str | None = "GOVERNED_SEMANTIC"
    connector_type: str | None = "postgres"


def _semantic_context(model_id: str) -> list[dict[str, str]]:
    return [{"type": "semantic_model", "id": model_id, "name": MODEL_NAME}]


def build_chat_payload(
    *,
    model_id: str,
    session_id: str,
    scenario: AskScenario,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "session_id": session_id,
        "question": scenario.question,
        "provider": "qwen",
        "model": "/models/Qwen3.8-27B-AWQ",
    }
    if scenario.attach_semantic:
        payload["context_sources"] = _semantic_context(model_id)
    else:
        payload["context_sources"] = []
    return payload


def evaluate_scenario(body: dict[str, Any], scenario: AskScenario) -> tuple[bool, list[str]]:
    errors: list[str] = []
    status = str(body.get("status") or "")
    if status != scenario.expect_status:
        errors.append(f"status={status!r} expected {scenario.expect_status!r}")

    tier = body.get("presentation_tier")
    if tier is not None:
        try:
            t = int(tier)
            if t < scenario.min_presentation_tier or t > scenario.max_presentation_tier:
                errors.append(
                    f"presentation_tier={t} outside [{scenario.min_presentation_tier}, {scenario.max_presentation_tier}]"
                )
        except (TypeError, ValueError):
            errors.append(f"presentation_tier invalid: {tier!r}")

    data = body.get("data") or {}
    row_count = int(data.get("row_count") or len(data.get("rows") or []))
    if row_count < scenario.min_rows:
        errors.append(f"row_count={row_count} < min_rows={scenario.min_rows}")
    if scenario.max_rows is not None and row_count > scenario.max_rows:
        errors.append(f"row_count={row_count} > max_rows={scenario.max_rows}")

    sql = str(body.get("governed_sql") or "")
    if scenario.require_governed_sql and not sql.strip():
        errors.append("missing governed_sql")
    for token in scenario.sql_must_contain:
        if token.casefold() not in sql.casefold():
            errors.append(f"governed_sql missing {token!r}")
    for token in scenario.sql_must_not_contain:
        if token.casefold() in sql.casefold():
            errors.append(f"governed_sql must not contain {token!r}")

    if scenario.context_mode and body.get("context_mode") != scenario.context_mode:
        errors.append(f"context_mode={body.get('context_mode')!r} expected {scenario.context_mode!r}")
    if scenario.connector_type and data.get("connector_type") != scenario.connector_type:
        errors.append(f"connector_type={data.get('connector_type')!r} expected {scenario.connector_type!r}")

    chart = body.get("chart_spec") or {}
    chart_type = chart.get("type") if isinstance(chart, dict) else None
    if scenario.chart_types and chart_type not in scenario.chart_types:
        errors.append(f"chart_spec.type={chart_type!r} not in {scenario.chart_types!r}")

    return not errors, errors


ASK_TIER_SCENARIOS: tuple[AskScenario, ...] = (
    AskScenario(
        key="tier1_active_customers",
        question="How many active customers are there?",
        min_presentation_tier=1,
        max_presentation_tier=2,
        min_rows=1,
        max_rows=1,
        require_governed_sql=True,
        sql_must_contain=("COUNT",),
        chart_types=("kpi", None),
    ),
    AskScenario(
        key="tier1_active_customers_id",
        question="Berapa jumlah nasabah aktif saat ini?",
        min_presentation_tier=1,
        max_presentation_tier=2,
        min_rows=1,
        max_rows=1,
        require_governed_sql=True,
        sql_must_contain=("COUNT", "customer"),
        sql_must_not_contain=("SUM(customer_id)",),
    ),
    AskScenario(
        key="tier2_by_channel",
        question="Show total transaction amount by channel.",
        min_presentation_tier=2,
        max_presentation_tier=3,
        min_rows=2,
        require_governed_sql=True,
        sql_must_contain=("GROUP BY", "channel"),
    ),
    AskScenario(
        key="tier3_rank_segments",
        question="Top 10 customer segments by total transaction amount.",
        min_presentation_tier=3,
        max_presentation_tier=3,
        min_rows=1,
        require_governed_sql=True,
        sql_must_contain=("segment",),
    ),
    AskScenario(
        key="tier3_monthly_transactions_id",
        question="Tampilkan jumlah transaksi per bulan (12 bulan terakhir).",
        min_presentation_tier=2,
        max_presentation_tier=3,
        min_rows=2,
        require_governed_sql=True,
        sql_must_contain=("transaction",),
    ),
    AskScenario(
        key="guardrail_python_ml",
        question="bisa bantu keluarkan contoh python code untuk bikin machine learning ?",
        attach_semantic=False,
        expect_status="UNSUPPORTED",
        min_presentation_tier=1,
        max_presentation_tier=1,
        require_governed_sql=False,
        context_mode=None,
        connector_type=None,
    ),
)

TIER_EVIDENCE_PATH = "testing/evidence/golden-path/PHASE3-SEMANTIC/banking-ask-tier-matrix.json"

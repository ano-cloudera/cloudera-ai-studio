"""Gemini rubric judge for live management UAT (answer quality, not just HTTP status)."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from pydantic import AliasChoices, BaseModel, Field

from app.core.config import Settings, get_settings
from app.llm.base import ProviderError
from app.llm.registry import ProviderRegistry


class UATAnswerVerdict(BaseModel):
    """Structured verdict from the UAT judge model."""

    acceptable: bool = Field(validation_alias=AliasChoices("acceptable", "pass"))
    score: int = Field(ge=1, le=10, description="1=poor, 10=excellent for management demo")
    grounded_in_data: bool = Field(
        description="Answer aligns with returned rows / governed query; no fabricated KPIs"
    )
    domain_appropriate: bool = Field(
        description="Sell-in vs sell-out, Alfamart/B2B channel, clarification when needed"
    )
    follow_up_coherent: bool | None = Field(
        default=None,
        description="For turn 2+: respects prior turn context; null on first turn",
    )
    issues: list[str] = Field(default_factory=list)
    summary: str = Field(description="One short paragraph for management UAT report")


def compact_chat_response(body: dict[str, Any], *, max_rows: int = 8) -> dict[str, Any]:
    data = body.get("data") if isinstance(body.get("data"), dict) else {}
    rows = data.get("rows") if isinstance(data.get("rows"), list) else []
    sample = [row for row in rows[:max_rows] if isinstance(row, dict)]
    answer = body.get("answer") if isinstance(body.get("answer"), dict) else {}
    return {
        "status": body.get("status"),
        "strategy": body.get("strategy"),
        "row_count": data.get("row_count"),
        "columns": data.get("columns"),
        "sample_rows": sample,
        "direct_answer": answer.get("direct_answer"),
        "executive_summary": answer.get("executive_summary"),
        "insights": (answer.get("insights") or [])[:6],
        "caveats": answer.get("caveats") or [],
        "data_reference": answer.get("data_reference"),
    }


def _default_criteria(status: str, strategy: str) -> list[str]:
    base = [
        "Scope TEMPO commercial analytics Q4 2024 (Oct–Dec 2024).",
        "Bahasa jawaban layak untuk audience management (jelas, tidak hallucinate angka di luar data).",
    ]
    if status == "CLARIFICATION" or strategy == "clarification":
        base.append(
            "Untuk CLARIFICATION: jangan mengarang hasil analitik; minta user memilih/meluruskan metrik atau grain."
        )
    else:
        base.append(
            "Untuk SUCCESS governed: jawaban harus konsisten dengan sample_rows / row_count (ranking, top N, atau agregat)."
        )
    return base


async def judge_management_turn(
    *,
    question: str,
    response: dict[str, Any],
    scenario_title: str,
    turn_index: int,
    prior_turns: list[dict[str, Any]] | None = None,
    extra_criteria: list[str] | None = None,
    min_score: int = 7,
    settings: Settings | None = None,
    judge_provider: str = "gemini",
) -> tuple[UATAnswerVerdict | None, str | None]:
    """
    Returns (verdict, error). error is set when judge could not run (missing API key, etc.).
    """
    settings = settings or get_settings()
    registry = ProviderRegistry(settings)
    models = registry.list_models()
    match = next((m for m in models if m.provider == judge_provider and m.available), None)
    if match is None:
        reason = next(
            (m.reason for m in models if m.provider == judge_provider),
            "judge provider unavailable",
        )
        return None, reason or "judge unavailable"

    provider = registry.resolve(judge_provider, match.id)
    criteria = _default_criteria(
        str(response.get("status") or ""),
        str(response.get("strategy") or ""),
    )
    if extra_criteria:
        criteria.extend(extra_criteria)

    payload = {
        "scenario_title": scenario_title,
        "turn_index": turn_index,
        "question": question,
        "prior_turns": prior_turns or [],
        "response": compact_chat_response(response),
        "rubric_criteria": criteria,
        "min_score_to_pass": min_score,
        "business_context": {
            "alfamart_b2b": "Alfamart/B2B = partner Sell-Out channel; cabang/DC = kolom branch (e.g. DC Palembang), bukan filter branch='Alfamart'.",
            "sell_in": "Sell-in = Tempo ke customer (sales office, material Tempo).",
            "follow_up": "Turn 2+ may reference prior ranking; honest caveats on grain limits are acceptable if disclosed.",
        },
        "instructions": (
            "You are an independent UAT reviewer for a TEMPO Ask Data PoC. "
            f"Set pass=true only if score>={min_score}, grounded_in_data and domain_appropriate are true, "
            "and issues are not blockers for a management demo. "
            "For turn 1 set follow_up_coherent=null; for turn 2+ set true/false. "
            "Set acceptable=true only when the answer is demo-ready for management."
        ),
    }

    last_error: str | None = None
    verdict: UATAnswerVerdict | None = None
    for attempt in range(4):
        try:
            verdict = await provider.generate_structured(
                [
                    {
                        "role": "system",
                        "content": "You evaluate assistant answers for enterprise data UAT. Be strict on fabricated numbers and wrong commercial domain (sell-in vs sell-out).",
                    },
                    {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
                ],
                UATAnswerVerdict,
                temperature=0.1,
                max_tokens=900,
            )
            last_error = None
            break
        except ProviderError as exc:
            last_error = str(exc)
            if attempt < 3:
                await asyncio.sleep(2.0 * (attempt + 1))
        except Exception as exc:  # noqa: BLE001
            return None, f"judge_failed:{type(exc).__name__}"
    if verdict is None:
        return None, last_error or "judge unavailable"

    # Normalize pass vs score
    if verdict.score < min_score or not verdict.grounded_in_data or not verdict.domain_appropriate:
        verdict = verdict.model_copy(update={"acceptable": False})
    return verdict, None

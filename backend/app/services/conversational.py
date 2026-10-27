"""LLM turn understanding: conversational vs analytic, follow-ups, clarifications."""

from __future__ import annotations

import json
import logging
import re
from enum import Enum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.llm.base import LLMProvider, ProviderError

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"

ClarificationChoice = Literal["", "sell-in", "sell-out", "picking", "unloading"]

# Mid-thread analytic turns with no catalog/clarification do not need an LLM call.
_SKIP_MIN_QUESTION_CHARS = 20
# Lite + clarification modes (first turn, short replies)—keep output compact.
_MAX_TOKENS_SIMPLE = 250


class TurnUnderstanding(BaseModel):
    is_conversational: bool = Field(
        description="True if greeting/capability/concept only—no governed SQL."
    )
    attach_domain_catalog: bool = Field(
        description="True to attach governed domain capability bullets in greeting path."
    )
    pipeline_question: str = Field(
        description="Self-contained question for the analytic pipeline (often same as user text)."
    )
    clarification_choice: ClarificationChoice = Field(
        default="",
        description="When user answers a prior clarification chip: sell-in, sell-out, picking, unloading.",
    )
    referential_follow_up: bool = Field(
        default=False,
        description="User refers to prior turn results (that branch, rank 1 vs last, drill products).",
    )
    follow_up_entity_id: str | None = None
    follow_up_entity_dimension: str | None = None
    follow_up_rank: int | None = Field(default=None, ge=1, le=100)
    follow_up_material_drill: bool = False
    follow_up_top_n: int | None = Field(default=None, ge=1, le=25)
    rationale: str = Field(default="", description="Short debug note.")


class _TurnUnderstandingLite(BaseModel):
    is_conversational: bool
    attach_domain_catalog: bool
    pipeline_question: str
    rationale: str = ""


class _TurnUnderstandingClarify(BaseModel):
    clarification_choice: ClarificationChoice = ""
    pipeline_question: str
    rationale: str = ""


class _TurnUnderstandingFollowUp(BaseModel):
    pipeline_question: str
    referential_follow_up: bool = False
    follow_up_entity_id: str | None = None
    follow_up_entity_dimension: str | None = None
    follow_up_rank: int | None = Field(default=None, ge=1, le=100)
    follow_up_material_drill: bool = False
    follow_up_top_n: int | None = Field(default=None, ge=1, le=25)
    is_conversational: bool = False
    rationale: str = ""


class UnderstandingMode(str, Enum):
    SKIP = "skip"
    LITE = "lite"
    CLARIFY = "clarify"
    FOLLOW_UP = "follow_up"


ConversationalIntent = TurnUnderstanding


def _read_prompt(name: str) -> str:
    return (PROMPTS_DIR / name).read_text(encoding="utf-8")


def _truncate(text: str | None, limit: int) -> str | None:
    if not text:
        return None
    text = str(text).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def _session_block(history: list[dict[str, Any]]) -> dict[str, Any]:
    from app.services.follow_up import analysis_context_from_history
    from app.services.session_context import last_turn_awaiting_clarification

    ctx = analysis_context_from_history(history)
    catalog = list(ctx.get("result_catalog") or [])[:8]
    pending = bool(history and last_turn_awaiting_clarification(history))
    block: dict[str, Any] = {
        "first_turn": not bool(history),
        "prior_clarification_pending": pending,
        "last_metric": ctx.get("last_metric"),
        "last_question": _truncate(ctx.get("last_question"), 200),
        "active_grain": ctx.get("active_grain"),
        "result_catalog": catalog,
    }
    if pending and history:
        last = history[-1]
        answer = last.get("answer") if isinstance(last.get("answer"), dict) else {}
        block["prior_question"] = _truncate(last.get("question"), 300)
        block["assistant_clarification"] = _truncate(
            " ".join(
                p
                for p in (
                    answer.get("direct_answer"),
                    answer.get("executive_summary"),
                )
                if p
            ),
            500,
        )
    elif history:
        block["conversation_history"] = [
            {
                "question": _truncate(item.get("question"), 160),
                "direct_answer": _truncate((item.get("answer") or {}).get("direct_answer"), 160),
            }
            for item in history[-2:]
            if isinstance(item, dict)
        ]
    return block


def _is_capability_meta_question(question: str) -> bool:
    """Greeting or mid-thread “what else can you help with?” — no governed SQL."""
    lowered = question.casefold().replace("–", "-")
    if any(
        term in lowered
        for term in ("top ", "berapa total", "ranking", "hitung", "tampilkan top", "urutkan")
    ):
        return False
    return any(
        term in lowered
        for term in (
            "data apa saja",
            "bisa ditanyakan",
            "bisa tanya",
            "what can i ask",
            "capabilities",
            "capability",
            "domain apa",
            "fitur apa",
            "bisa bantu apa",
            "bantu apa lagi",
            "kamu bisa apa lagi",
            "bisa apa lagi ya",
            "apa lagi ya",
            "apa lagi selain",
            "selain data ini",
            "selain data ",
            "what else",
            "help with besides",
            "kamu bisa apa",
        )
    )


def _is_capability_overview(question: str) -> bool:
    return _is_capability_meta_question(question)


def _is_promo_proxy_explain_follow_up(question: str, history: list[dict[str, Any]]) -> bool:
    lowered = question.casefold()
    if not any(term in lowered for term in ("jelaskan", "explain", "proxy", "nov vs", "november")):
        return False
    # Governed follow-ups may mention "uplift proxy" without asking for a concept essay.
    if any(term in lowered for term in ("top ", "top", "ranking", "urutan", "material", "produk")):
        return False
    if "status dominan" in lowered or "dominan tadi" in lowered or "dominan dari" in lowered:
        return False
    if "tadi" in lowered and any(term in lowered for term in ("uplift", "material", "status")):
        return False
    if not history:
        return False
    from app.services.follow_up import analysis_context_from_history

    ctx = analysis_context_from_history(history)
    metric = str(ctx.get("last_metric") or "").casefold()
    return "promo" in metric or "uplift" in metric


def _is_sell_in_vs_sell_out_concept(question: str) -> bool:
    lowered = question.casefold().replace("–", "-")
    asks_contrast = any(term in lowered for term in ("beda", "bedanya", "perbedaan", "difference", "vs "))
    mentions_sell_in = any(term in lowered for term in ("sell-in", "sell in", "sellin"))
    mentions_sell_out = any(term in lowered for term in ("sell-out", "sell out", "sellout", "alfamart"))
    looks_analytic = any(term in lowered for term in ("top ", "berapa", "ranking", "total ", "q4 2024"))
    return asks_contrast and mentions_sell_in and mentions_sell_out and not looks_analytic


def _is_analytic_escape_from_clarification(question: str) -> bool:
    """User narrows to a concrete governed ask after a clarification turn."""
    lowered = question.casefold().replace("–", "-")
    if any(term in lowered for term in ("cukup", "cukup tampilkan", "just show", "tampilkan saja")):
        if any(term in lowered for term in ("sell-in", "sell in", "sellin")):
            return True
    if re.search(r"\bFE\d+\b", question, flags=re.IGNORECASE) and any(
        term in lowered for term in ("sell-in", "sell in", "per bulan", "bulanan")
    ):
        return True
    return False


def _understanding_mode(session: dict[str, Any], question: str) -> UnderstandingMode:
    if session.get("prior_clarification_pending"):
        if _is_analytic_escape_from_clarification(question):
            return UnderstandingMode.SKIP
        return UnderstandingMode.CLARIFY
    if session.get("result_catalog"):
        return UnderstandingMode.FOLLOW_UP
    if session.get("first_turn"):
        return UnderstandingMode.LITE
    if session.get("last_metric"):
        return UnderstandingMode.LITE
    if len(question.strip()) >= _SKIP_MIN_QUESTION_CHARS:
        return UnderstandingMode.SKIP
    return UnderstandingMode.LITE


def _default_analytic(question: str, *, rationale: str) -> TurnUnderstanding:
    return TurnUnderstanding(
        is_conversational=False,
        attach_domain_catalog=False,
        pipeline_question=question.strip(),
        rationale=rationale,
    )


def _merge_pipeline(result: TurnUnderstanding, question: str) -> TurnUnderstanding:
    if not (result.pipeline_question or "").strip():
        return result.model_copy(update={"pipeline_question": question.strip()})
    return result


async def _call_structured(
    provider: LLMProvider,
    *,
    prompt_file: str,
    payload: dict[str, Any],
    response_model: type[BaseModel],
    max_tokens: int,
) -> BaseModel:
    return await provider.generate_structured(
        [
            {"role": "system", "content": _read_prompt(prompt_file)},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ],
        response_model,
        temperature=0.0,
        max_tokens=max_tokens,
    )


async def understand_turn(
    *,
    provider: LLMProvider,
    question: str,
    conversation_history: list[dict[str, Any]] | None = None,
) -> TurnUnderstanding:
    history = conversation_history or []
    session = _session_block(history)
    mode = _understanding_mode(session, question)
    q = question.strip()

    if mode == UnderstandingMode.SKIP:
        logger.debug("turn_understanding mode=skip chars=%s", len(q))
        return _default_analytic(q, rationale="skip_session_has_no_catalog_or_clarify")

    if session.get("first_turn") and _is_sell_in_vs_sell_out_concept(q):
        return TurnUnderstanding(
            is_conversational=True,
            attach_domain_catalog=False,
            pipeline_question=q,
            rationale="concept_sell_in_vs_sell_out",
        )

    if _is_capability_meta_question(q):
        return TurnUnderstanding(
            is_conversational=True,
            attach_domain_catalog=True,
            pipeline_question=q,
            rationale="capability_overview" if session.get("first_turn") else "capability_follow_up",
        )

    if _is_promo_proxy_explain_follow_up(q, history):
        return TurnUnderstanding(
            is_conversational=True,
            attach_domain_catalog=False,
            pipeline_question=q,
            rationale="promo_proxy_explain",
        )

    try:
        if mode == UnderstandingMode.CLARIFY:
            raw = await _call_structured(
                provider,
                prompt_file="turn_understanding_clarify.md",
                payload={"question": q, "session": session},
                response_model=_TurnUnderstandingClarify,
                max_tokens=_MAX_TOKENS_SIMPLE,
            )
            result = TurnUnderstanding(
                is_conversational=False,
                attach_domain_catalog=False,
                pipeline_question=raw.pipeline_question,
                clarification_choice=raw.clarification_choice,
                rationale=raw.rationale or "mode_clarify",
            )
        elif mode == UnderstandingMode.FOLLOW_UP:
            raw = await _call_structured(
                provider,
                prompt_file="turn_understanding_followup.md",
                payload={"question": q, "session": session},
                response_model=_TurnUnderstandingFollowUp,
                max_tokens=320,
            )
            result = TurnUnderstanding(
                is_conversational=raw.is_conversational,
                attach_domain_catalog=False,
                pipeline_question=raw.pipeline_question,
                referential_follow_up=raw.referential_follow_up,
                follow_up_entity_id=raw.follow_up_entity_id,
                follow_up_entity_dimension=raw.follow_up_entity_dimension,
                follow_up_rank=raw.follow_up_rank,
                follow_up_material_drill=raw.follow_up_material_drill,
                follow_up_top_n=raw.follow_up_top_n,
                rationale=raw.rationale or "mode_follow_up",
            )
        else:
            raw = await _call_structured(
                provider,
                prompt_file="turn_understanding_lite.md",
                payload={"question": q, "session": session},
                response_model=_TurnUnderstandingLite,
                max_tokens=_MAX_TOKENS_SIMPLE,
            )
            result = TurnUnderstanding(
                is_conversational=raw.is_conversational,
                attach_domain_catalog=raw.attach_domain_catalog,
                pipeline_question=raw.pipeline_question,
                rationale=raw.rationale or "mode_lite",
            )
        logger.debug("turn_understanding mode=%s rationale=%s", mode.value, result.rationale[:80])
        return _merge_pipeline(result, q)
    except ProviderError:
        return _default_analytic(q, rationale="turn_understanding_failed_default_analytic")


async def classify_conversational_intent(
    *,
    provider: LLMProvider,
    question: str,
    first_turn: bool,
    conversation_history: list[dict[str, Any]] | None = None,
) -> TurnUnderstanding:
    _ = first_turn
    return await understand_turn(
        provider=provider,
        question=question,
        conversation_history=conversation_history,
    )


def turn_understanding_from_state(state: dict[str, Any]) -> TurnUnderstanding | None:
    raw = state.get("turn_understanding") or state.get("conversational_intent")
    if not isinstance(raw, dict):
        return None
    try:
        return TurnUnderstanding.model_validate(raw)
    except Exception:
        return None


def conversational_intent_from_state(state: dict[str, Any]) -> TurnUnderstanding | None:
    return turn_understanding_from_state(state)

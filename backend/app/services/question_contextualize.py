"""Apply LLM turn understanding to the pipeline question (no keyword heuristics)."""

from __future__ import annotations

from typing import Any

from app.services.conversational import TurnUnderstanding
from app.services.follow_up import (
    analysis_context_from_history,
    try_follow_up_governed_resolution,
)
from app.services.session_context import last_turn_awaiting_clarification


def governed_follow_up_keeps_literal_question(
    question: str,
    history: list[dict],
    *,
    understanding: TurnUnderstanding | None = None,
) -> bool:
    """Governed drill-down resolves via session context; skip long LLM rewrites."""
    if not history:
        return False
    ctx = analysis_context_from_history(history)
    return bool(try_follow_up_governed_resolution(question, ctx, understanding))


def resolve_question_for_pipeline(
    raw_question: str,
    history: list[dict],
    understanding: TurnUnderstanding,
) -> str:
    """Prefer literal question when governed follow-up binding succeeds; else LLM pipeline text."""
    if history and governed_follow_up_keeps_literal_question(
        raw_question, history, understanding=understanding
    ):
        return raw_question.strip()
    return apply_turn_understanding(raw_question, history, understanding)


def apply_turn_understanding(
    raw_question: str,
    history: list[dict],
    understanding: TurnUnderstanding,
) -> str:
    pipeline = (understanding.pipeline_question or raw_question).strip()
    choice = (understanding.clarification_choice or "").strip()
    if history and last_turn_awaiting_clarification(history):
        if pipeline and pipeline != raw_question.strip() and "Klarifikasi pengguna" in pipeline:
            return pipeline
        previous_question = str(history[-1].get("question") or "").strip()
        if previous_question and choice:
            if choice in ("picking", "unloading"):
                selected = raw_question.strip()
            else:
                selected = choice
            return f"{previous_question}\nKlarifikasi pengguna: {selected}"
    return pipeline or raw_question.strip()


def understanding_from_dict(data: dict[str, Any] | None) -> TurnUnderstanding | None:
    if not isinstance(data, dict):
        return None
    try:
        return TurnUnderstanding.model_validate(data)
    except Exception:
        return None

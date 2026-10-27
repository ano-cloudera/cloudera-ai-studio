"""Lightweight Ask Data guardrails (no LLM)."""

from __future__ import annotations

import re
from typing import Any

_CODE_OR_ML_PATTERNS = (
    r"\bpython\b",
    r"\bjavascript\b",
    r"\bjava\b(?!\s+script)",
    r"\bmachine learning\b",
    r"\bdeep learning\b",
    r"\bsklearn\b",
    r"\bscikit[\s-]learn\b",
    r"\btensorflow\b",
    r"\bpytorch\b",
    r"\bkaggle\b",
    r"\bcontoh code\b",
    r"\bcontoh kode\b",
    r"\bsource code\b",
    r"\bgenerate code\b",
    r"\bkeluarkan code\b",
    r"\bkeluarkan kode\b",
    r"\bscript\b",
    r"\bapi endpoint\b",
    r"\brest api\b",
)

_COAXING_AFTER_REFUSAL_PATTERNS = (
    r"\bkeluarin aja\b",
    r"\bkeluarkan aja\b",
    r"\bbuatin aja\b",
    r"\bbuatkan aja\b",
    r"\bayo dong\b",
    r"\btetap (?:kasih|keluarkan|buatin|buatin)\b",
    r"\bjust (?:give|show|output)\b",
    r"\bcome on\b",
    r"\bignore (?:the )?(?:rules|policy|guardrail)\b",
    r"\bskip (?:the )?(?:guardrail|policy)\b",
)

_GOVERNED_ANALYTICS_HINTS = (
    "transaction",
    "customer",
    "amount",
    "channel",
    "metric",
    "total",
    "berapa",
    "show",
    "break",
    "breakdown",
    "count",
    "rate",
    "segment",
    "region",
    "trend",
    "compare",
    "top ",
    "failed",
    "distinct",
    "by ",
)


def is_out_of_scope_question(question: str) -> bool:
    """Requests outside governed analytics (coding, generic ML tutorials, etc.)."""
    text = " ".join((question or "").casefold().split())
    if not text:
        return False
    if any(re.search(pat, text) for pat in _CODE_OR_ML_PATTERNS):
        return True
    if "machine learning" in text or ("model" in text and "semantic" not in text and "data" not in text):
        if any(t in text for t in ("python", "code", "kode", "train", "latih")):
            return True
    return False


def out_of_scope_message() -> str:
    return (
        "Saya fokus membantu analisis data melalui semantic layer dan metric yang dipublish "
        "(contoh: total customer, trend transaksi, perbandingan region). "
        "Untuk contoh kode Python atau machine learning di luar data governed, "
        "gunakan dokumentasi atau tim engineering."
    )


def is_out_of_scope_coaxing(question: str) -> bool:
    text = " ".join((question or "").casefold().split())
    if not text:
        return False
    return any(re.search(pat, text) for pat in _COAXING_AFTER_REFUSAL_PATTERNS)


def _history_answer_ref(entry: dict[str, Any]) -> str:
    answer = entry.get("answer")
    if isinstance(answer, dict):
        return str(answer.get("data_reference") or "").casefold()
    return ""


def last_turn_out_of_scope_refusal(history: list[dict[str, Any]]) -> bool:
    """Prior turn was an explicit Ask Data scope refusal (coding / ML / etc.)."""
    if not history:
        return False
    last = history[-1]
    status = str(last.get("status") or "").upper()
    strategy = str(last.get("strategy") or "").casefold()
    if status != "UNSUPPORTED" or strategy != "unsupported":
        return False
    if _history_answer_ref(last) == "ask_data_scope":
        return True
    prev_q = str(last.get("question") or "")
    return is_out_of_scope_question(prev_q)


def lacks_governed_analytic_intent(question: str) -> bool:
    """Short/vague text with no governed analytics cue (used after a scope refusal)."""
    text = " ".join((question or "").casefold().split())
    if not text:
        return True
    if any(hint in text for hint in _GOVERNED_ANALYTICS_HINTS):
        return False
    return len(text.split()) <= 10


def should_block_ask_data_scope(
    question: str,
    *,
    raw_question: str | None = None,
    history: list[dict[str, Any]] | None = None,
) -> bool:
    """Primary Ask Data scope gate: coding/ML requests and post-refusal coaxing."""
    candidates = [question, raw_question or ""]
    if any(is_out_of_scope_question(item) for item in candidates if item.strip()):
        return True
    hist = history or []
    if not last_turn_out_of_scope_refusal(hist):
        return False
    probe = (raw_question or question).strip()
    if not probe:
        return False
    if is_out_of_scope_coaxing(probe):
        return True
    return lacks_governed_analytic_intent(probe)

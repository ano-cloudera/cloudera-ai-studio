"""Unified capability examples for Ask Data (starters, greeting insights, empty state)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.core.config import Settings, get_settings

if TYPE_CHECKING:
    from app.semantic.context import SemanticContextService

# Optional curated NL examples (vertical demos); generic metrics still work without these.
_REGISTRY_METRIC_EXAMPLES: dict[str, str] = {
    "customers_customer_id_total": "Berapa total customer kita saat ini?",
    "transactions_transaction_id_total": "Trend jumlah transaksi per bulan (12 bulan terakhir).",
    "transactions_amount_total": "Tampilkan total nominal transaksi per channel.",
    "transactions_failed_transaction_rate": "Berapa failed transaction rate?",
    "transactions_customer_id_total": "Berapa unique customer yang punya transaksi?",
}

_REGISTRY_METRIC_EXAMPLES_EN: dict[str, str] = {
    "customers_customer_id_total": "How many customers do we have today?",
    "transactions_transaction_id_total": "Show the monthly trend of transaction count (last 12 months).",
    "transactions_amount_total": "Show total transaction amount by channel.",
    "transactions_failed_transaction_rate": "What is the failed transaction rate?",
    "transactions_customer_id_total": "How many unique customers have transactions?",
}

def uses_published_metric_catalog(ctx: SemanticContextService) -> bool:
    """True when the capability menu should come from published metrics."""
    return bool(ctx.metrics)


def example_question_for_metric(name: str, label: str, language: str = "en") -> str:
    english = language != "id"
    curated = _REGISTRY_METRIC_EXAMPLES_EN if english else _REGISTRY_METRIC_EXAMPLES
    if name in curated:
        return curated[name]
    lowered = name.casefold()
    if "customer" in lowered and "transaction" not in lowered:
        return (
            "Compare the number of customers by segment or status."
            if english
            else "Bandingkan jumlah customer per segment atau status."
        )
    if "transaction" in lowered and "amount" in lowered:
        return curated["transactions_amount_total"]
    if "transaction" in lowered and "rate" in lowered:
        return curated["transactions_failed_transaction_rate"]
    if "transaction" in lowered:
        return (
            "Top 5 customer segments by transaction count."
            if english
            else "Top 5 customer segment berdasarkan jumlah transaksi."
        )
    return f"Show the trend or breakdown for {label}." if english else f"Tampilkan trend atau breakdown untuk {label}."


def _dedupe_questions(candidates: list[str], *, limit: int) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in candidates:
        text = " ".join(str(raw).split()).strip()
        if not text:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
        if len(out) >= limit:
            break
    return out


def resolve_example_questions(
    ctx: SemanticContextService,
    *,
    configured_starters: list[str] | None = None,
    exclude_focus: str | None = None,
    limit: int = 6,
    settings: Settings | None = None,
    language: str = "en",
) -> list[str]:
    """Plain question texts — shared by starters API and capability insights."""
    from app.semantic.context import guidance_focus_from_metric

    if configured_starters:
        custom = _dedupe_questions(list(configured_starters), limit=limit)
        if custom:
            return custom

    golden: list[str] = []
    for item in ctx.registry.golden_questions.get("questions", []):
        if item.get("expected_status") not in {"supported", "supported_with_caveat"}:
            continue
        question = str(item.get("question") or "").strip()
        if not question:
            continue
        metric = item.get("metric")
        if exclude_focus and metric and guidance_focus_from_metric(str(metric)) == exclude_focus:
            continue
        golden.append(question)
    golden = _dedupe_questions(golden, limit=limit)
    if golden:
        return golden

    summary_examples = list(ctx.registry.capability_summary().get("examples") or [])
    summary_examples = _dedupe_questions(summary_examples, limit=limit)
    if summary_examples:
        return summary_examples

    if uses_published_metric_catalog(ctx):
        from app.ask_data.metric_labels import humanize_metric_label

        auto: list[str] = []
        for name in sorted(ctx.metrics):
            if exclude_focus and guidance_focus_from_metric(name) == exclude_focus:
                continue
            if ctx.registry.metric_configs.get(name, {}).get("governance_status") == "reference":
                continue  # placeholder metric of the neutral reference project; never suggest it
            try:
                definition = ctx.metric_definition(name)
            except Exception:
                definition = {}
            label = humanize_metric_label(name=name, definition=definition)
            auto.append(example_question_for_metric(name, label, language))
            if len(auto) >= limit:
                break
        auto = _dedupe_questions(auto, limit=limit)
        if auto:
            return auto

    if language == "id":
        return [
            "Ajukan KPI atau total dari metric yang dipublish.",
            "Minta breakdown per dimensi yang tersedia di semantic model.",
            "Minta ranking atau trend untuk periode tertentu.",
        ][:limit]
    return [
        "Ask for a KPI or total from a published metric.",
        "Ask for a breakdown by a dimension available in the semantic model.",
        "Ask for a ranking or trend over a specific period.",
    ][:limit]


def insight_lines_from_questions(questions: list[str], language: str = "en") -> list[str]:
    prefix = "Contoh pertanyaan" if language == "id" else "Example question"
    return [f"{prefix}: {q}" for q in questions]


def resolve_capability_insight_lines(
    ctx: SemanticContextService,
    *,
    configured_starters: list[str] | None = None,
    exclude_focus: str | None = None,
    limit: int = 6,
    settings: Settings | None = None,
    language: str = "en",
) -> list[str]:
    """Formatted bullets for AnalysisOutput.insights on capability turns."""
    settings = settings or get_settings()
    if configured_starters:
        starter_lines = insight_lines_from_questions(
            _dedupe_questions(list(configured_starters), limit=limit), language
        )
        if starter_lines:
            return starter_lines

    if uses_published_metric_catalog(ctx):
        from app.ask_data.metric_labels import humanize_metric_label
        from app.semantic.context import guidance_focus_from_metric

        lines = []
        for name in sorted(ctx.metrics):
            if exclude_focus and guidance_focus_from_metric(name) == exclude_focus:
                continue
            try:
                definition = ctx.metric_definition(name)
            except Exception:
                definition = {}
            label = humanize_metric_label(name=name, definition=definition)
            example = example_question_for_metric(name, label, language)
            if language == "id":
                lines.append(f"{label}: KPI, trend, atau breakdown dimensi. Contoh: {example}")
            else:
                lines.append(f"{label}: KPI, trend, or breakdown by dimension. Example: {example}")
            if len(lines) >= limit:
                break
        if lines:
            return lines

    questions = resolve_example_questions(
        ctx,
        configured_starters=None,
        exclude_focus=exclude_focus,
        limit=limit,
        settings=settings,
        language=language,
    )
    return insight_lines_from_questions(questions, language)

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

_TEMPO_LEGACY_METRIC_MARKERS = frozenset(
    {
        "gross_billing_value",
        "stock_tempo_total_qty",
        "b2b_branch_sell_out_value",
        "sat_oos_rate",
        "average_picking_minutes",
        "promo_observation_count",
    }
)

_TEMPO_LEGACY_DOMAIN_OPTIONS: tuple[dict[str, Any], ...] = (
    {"name": "Sales / Sell-In", "metrics": ["gross_billing_value"], "examples": ["Berapa Gross Sales TEMPO selama Q4 2024?"]},
    {"name": "B2B / Sell-Out", "metrics": ["b2b_branch_sell_out_value"], "examples": ["Branch mana dengan nilai Sell-Out terbesar?"]},
    {"name": "Stock Tempo", "metrics": ["stock_tempo_total_qty"], "examples": ["Bagaimana tren stok gudang Tempo per bulan?"]},
    {
        "name": "Stock SAT (Alfamart)",
        "metrics": ["sat_dc_stock_quantity", "sat_store_stock_quantity"],
        "examples": ["Berapa stok DC Alfamart atau stok retail per division?"],
    },
    {"name": "SAT OOS", "metrics": ["sat_oos_rate"], "examples": ["Material mana dengan SAT OOS rate tertinggi?"]},
    {"name": "Service Level", "metrics": ["service_fill_rate"], "examples": ["Material mana dengan Fill Rate terendah?"]},
    {"name": "Picking", "metrics": ["average_picking_minutes"], "examples": ["Sales office mana dengan rata-rata picking terlama?"]},
    {"name": "Unloading", "metrics": ["average_unloading_minutes"], "examples": ["Sales office mana dengan rata-rata unloading terlama?"]},
    {"name": "SAT Promo", "metrics": ["promo_observation_count"], "examples": ["Berapa observasi promo aktif pada Desember 2024?"]},
)

_TEMPO_METRIC_HELP: dict[str, str] = {
    "gross_billing_value": "Gross Sales / Sell-In",
    "b2b_branch_sell_out_value": "nilai Sell-Out B2B per cabang",
    "stock_tempo_total_qty": "stok gudang Tempo",
    "sat_dc_stock_quantity": "stok DC partner (Alfamart)",
    "sat_store_stock_quantity": "stok toko retail",
    "sat_oos_rate": "tingkat OOS di toko SAT",
    "service_fill_rate": "service level / fill rate cabang",
    "average_picking_minutes": "durasi picking gudang",
    "average_unloading_minutes": "durasi unloading gudang",
    "promo_observation_count": "observasi promo aktif",
}

_TEMPO_DOMAIN_NAMES_BY_FOCUS: dict[str, frozenset[str]] = {
    "sales": frozenset({"Sales / Sell-In"}),
    "b2b": frozenset({"B2B / Sell-Out"}),
    "stock_tempo": frozenset({"Stock Tempo"}),
    "stock_sat": frozenset({"Stock SAT (Alfamart)"}),
    "oos": frozenset({"SAT OOS"}),
    "service_level": frozenset({"Service Level"}),
    "picking": frozenset({"Picking"}),
    "unloading": frozenset({"Unloading"}),
    "promo": frozenset({"SAT Promo"}),
    "stock": frozenset({"Stock Tempo", "Stock SAT (Alfamart)"}),
}


def legacy_tempo_capability_catalog_enabled(settings: Settings | None = None) -> bool:
    return bool(getattr(settings or get_settings(), "ask_data_legacy_tempo_capability_catalog", False))


def is_legacy_tempo_scan_catalog(metrics: dict[str, Any]) -> bool:
    keys = {str(k).casefold() for k in metrics}
    markers = {m.casefold() for m in _TEMPO_LEGACY_METRIC_MARKERS}
    return bool(keys & markers)


def uses_published_metric_catalog(ctx: SemanticContextService) -> bool:
    """Prefer published metrics over legacy TEMPO domain menu."""
    from app.semantic.banking_demo_catalog import is_banking_demo_registry

    if getattr(ctx, "_registry_runtime", False):
        return True
    if is_banking_demo_registry(ctx.datasets):
        return True
    if legacy_tempo_capability_catalog_enabled() and is_legacy_tempo_scan_catalog(ctx.metrics):
        return False
    return bool(ctx.metrics)


def example_question_for_metric(name: str, label: str) -> str:
    if name in _REGISTRY_METRIC_EXAMPLES:
        return _REGISTRY_METRIC_EXAMPLES[name]
    lowered = name.casefold()
    if "customer" in lowered and "transaction" not in lowered:
        return "Bandingkan jumlah customer per segment atau status."
    if "transaction" in lowered and "amount" in lowered:
        return "Tampilkan total nominal transaksi per channel."
    if "transaction" in lowered and "rate" in lowered:
        return "Berapa failed transaction rate?"
    if "transaction" in lowered:
        return "Top 5 customer segment berdasarkan jumlah transaksi."
    return f"Tampilkan trend atau breakdown untuk {label}."


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
            try:
                definition = ctx.metric_definition(name)
            except Exception:
                definition = {}
            label = humanize_metric_label(name=name, definition=definition)
            auto.append(example_question_for_metric(name, label))
            if len(auto) >= limit:
                break
        auto = _dedupe_questions(auto, limit=limit)
        if auto:
            return auto

    if legacy_tempo_capability_catalog_enabled(settings) and is_legacy_tempo_scan_catalog(ctx.metrics):
        skip = _TEMPO_DOMAIN_NAMES_BY_FOCUS.get(exclude_focus or "", frozenset())
        tempo: list[str] = []
        for option in _TEMPO_LEGACY_DOMAIN_OPTIONS:
            if option["name"] in skip:
                continue
            example = option["examples"][0] if option.get("examples") else ""
            if example:
                tempo.append(str(example))
        tempo = _dedupe_questions(tempo, limit=limit)
        if tempo:
            return tempo

    return [
        "Ajukan KPI atau total dari metric yang dipublish.",
        "Minta breakdown per dimensi yang tersedia di semantic model.",
        "Minta ranking atau trend untuk periode tertentu.",
    ][:limit]


def insight_lines_from_questions(questions: list[str]) -> list[str]:
    return [f"Contoh pertanyaan: {q}" for q in questions]


def resolve_capability_insight_lines(
    ctx: SemanticContextService,
    *,
    configured_starters: list[str] | None = None,
    exclude_focus: str | None = None,
    limit: int = 6,
    settings: Settings | None = None,
) -> list[str]:
    """Formatted bullets for AnalysisOutput.insights on capability turns."""
    settings = settings or get_settings()
    if configured_starters:
        starter_lines = insight_lines_from_questions(
            _dedupe_questions(list(configured_starters), limit=limit)
        )
        if starter_lines:
            return starter_lines

    if (
        legacy_tempo_capability_catalog_enabled(settings)
        and is_legacy_tempo_scan_catalog(ctx.metrics)
        and not uses_published_metric_catalog(ctx)
    ):
        skip = _TEMPO_DOMAIN_NAMES_BY_FOCUS.get(exclude_focus or "", frozenset())
        lines: list[str] = []
        for option in _TEMPO_LEGACY_DOMAIN_OPTIONS:
            if option["name"] in skip:
                continue
            helps = ", ".join(
                _TEMPO_METRIC_HELP.get(metric, metric.replace("_", " "))
                for metric in option["metrics"]
            )
            example = option["examples"][0] if option.get("examples") else ""
            lines.append(f"{option['name']}: {helps}. Contoh: {example}")
        return lines

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
            example = example_question_for_metric(name, label)
            lines.append(f"{label}: KPI, trend, atau breakdown dimensi. Contoh: {example}")
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
    )
    return insight_lines_from_questions(questions)

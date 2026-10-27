"""Deterministic one-line answers for picking/unloading superlative questions."""

from __future__ import annotations

from typing import Any


def deterministic_ops_duration_answer(
    question: str,
    metric: str | None,
    rows: list[dict[str, Any]],
) -> str | None:
    if not rows or not metric:
        return None
    lowered = (question or "").casefold()
    metric_folded = metric.casefold()
    if "picking" not in metric_folded and "unloading" not in metric_folded:
        return None
    company_avg = any(
        term in lowered
        for term in ("company-wide", "company wide", "seluruh perusahaan", "companywide", "nasional")
    ) and any(term in lowered for term in ("rata-rata", "rata rata", "average", "berapa"))
    if company_avg and len(rows) == 1 and isinstance(rows[0], dict) and "metric_value" in rows[0]:
        try:
            minutes_f = float(rows[0]["metric_value"])
        except (TypeError, ValueError):
            return None
        label = "picking" if "picking" in metric_folded else "unloading"
        return f"Rata-rata durasi {label} company-wide Q4 2024: {minutes_f:.2f} menit (agregat governed)."
    if not any(term in lowered for term in ("mana", "office", "cabang", "sales office")):
        return None
    if not any(
        term in lowered
        for term in (
            "tercepat",
            "efisien",
            "terlama",
            "terlambat",
            "tertinggi",
            "paling",
            "top",
            "terburuk",
        )
    ):
        return None
    row = rows[0]
    if not isinstance(row, dict):
        return None
    office_col = next((c for c in ("sales_office", "sales_off") if c in row), None)
    if not office_col:
        return None
    office = row.get(office_col)
    minutes = row.get("metric_value")
    if office is None or minutes is None:
        return None
    try:
        minutes_f = float(minutes)
    except (TypeError, ValueError):
        return None
    label = "picking" if "picking" in metric_folded else "unloading"
    direction = "tercepat/efisien"
    if any(term in lowered for term in ("terlama", "terlambat", "tertinggi", "terburuk")):
        direction = "terlama/tertinggi"
    elif any(term in lowered for term in ("tercepat", "efisien", "paling cepat")):
        direction = "tercepat/efisien"
    return (
        f"Sales office {office} memiliki rata-rata durasi {label} "
        f"{minutes_f:.2f} menit (baris #1 hasil query, urutan {direction})."
    )


def deterministic_ops_workload_answer(
    question: str,
    metric: str | None,
    rows: list[dict[str, Any]],
) -> str | None:
    """Event-row counts (unloading/picking workload), not duration minutes."""
    if not rows or not metric:
        return None
    if metric not in ("unloading_event_count", "picking_workload_rows"):
        return None
    lowered = (question or "").casefold()
    if not any(
        term in lowered
        for term in (
            "event",
            "jumlah",
            "banyak",
            "aktivitas",
            "workload",
            "terbanyak",
            "tertinggi",
            "dokumen",
            "baris",
        )
    ):
        return None
    row = rows[0]
    if not isinstance(row, dict):
        return None
    office_col = next((c for c in ("sales_office", "sales_off") if c in row), None)
    if not office_col:
        return None
    office = row.get(office_col)
    raw = row.get("metric_value")
    if office is None or raw is None:
        return None
    try:
        count = int(float(raw))
    except (TypeError, ValueError):
        return None
    label = "unloading" if "unloading" in metric else "picking"
    unit = "event unloading" if "unloading" in metric else "baris picking"
    return (
        f"Sales office {office} memiliki aktivitas {label} terbanyak Q4 2024: "
        f"{count:,} {unit} tercatat (peringkat #1 dari query governed)."
    )

"""Deterministic one-line summary of a governed result, used when the analysis model cannot answer."""
from __future__ import annotations

from typing import Any


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _fmt(value: float) -> str:
    if value == int(value) and abs(value) < 1e15:
        return f"{int(value):,}"
    return f"{value:,.2f}"


def _label(row: dict[str, Any], dimensions: list[str]) -> str:
    return " / ".join(str(row.get(d)) for d in dimensions)


def summarize_rows(rows: list[dict[str, Any]], *, language: str = "en") -> str:
    """Plain summary: the value for one row, or the highest and lowest groups for several."""
    if not rows or not isinstance(rows[0], dict):
        return ""
    columns = list(rows[0].keys())
    metric = "metric_value" if "metric_value" in columns else next(
        (c for c in reversed(columns) if _number(rows[0].get(c)) is not None), None
    )
    if metric is None:
        return ""
    dimensions = [c for c in columns if c != metric]
    id_lang = language == "id"
    if len(rows) == 1:
        value = _number(rows[0].get(metric))
        if value is None:
            return ""
        if not dimensions:
            return f"Hasilnya {_fmt(value)}." if id_lang else f"The result is {_fmt(value)}."
        label = _label(rows[0], dimensions)
        return f"{label}: {_fmt(value)}." if id_lang else f"{label}: {_fmt(value)}."
    scored = [(r, _number(r.get(metric))) for r in rows]
    scored = [(r, v) for r, v in scored if v is not None]
    if not scored:
        return ""
    top = max(scored, key=lambda item: item[1])
    low = min(scored, key=lambda item: item[1])
    count = len(rows)
    if not dimensions:
        return f"Query governed menghasilkan {count} baris." if id_lang else f"The governed query returned {count} rows."
    if id_lang:
        return (
            f"{count} kelompok. Tertinggi: {_label(top[0], dimensions)} ({_fmt(top[1])}); "
            f"terendah: {_label(low[0], dimensions)} ({_fmt(low[1])})."
        )
    return (
        f"{count} groups. Highest: {_label(top[0], dimensions)} ({_fmt(top[1])}); "
        f"lowest: {_label(low[0], dimensions)} ({_fmt(low[1])})."
    )

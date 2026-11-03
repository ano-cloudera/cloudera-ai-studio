"""A plain-language account of how an answer was calculated, taken from the plan and the executed SQL.

Nothing here comes from the language model: the metric, formula, breakdown, filters, period, source tables and the kind
of comparison are read from what actually ran, so the explanation is the same for every model and cannot be invented.
"""
from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Any

import sqlglot
from sqlglot import exp

from app.ask_data.metric_labels import humanize_metric_label
from app.core.models import CalculationCheck, CalculationNote

_ALIAS = re.compile(r"\bd\.")
_DATE_LITERAL = re.compile(r"(?:DATE\s*'|CAST\(\s*'|TIMESTAMP\s*')(\d{4}-\d{2}-\d{2})")


def _parse(sql: str) -> exp.Expression | None:
    try:
        return sqlglot.parse_one(sql, read="trino")
    except Exception:  # noqa: BLE001 - an unparsable statement just means a shorter note
        return None


def _conjuncts(node: exp.Expression | None) -> list[exp.Expression]:
    if node is None:
        return []
    if isinstance(node, exp.Where):
        return _conjuncts(node.this)
    if isinstance(node, exp.Paren) and isinstance(node.this, exp.And):
        return _conjuncts(node.this)
    if isinstance(node, exp.And):
        return [*_conjuncts(node.left), *_conjuncts(node.right)]
    return [node]


def readable_name(key: str, dataset: str | None = None) -> str:
    """`fulfillment_orders_region_name` -> `region name`."""
    name = key
    if dataset and name.startswith(f"{dataset}_"):
        name = name[len(dataset) + 1 :]
    return name.replace("_", " ").strip()


def _column(node: exp.Expression) -> str | None:
    return node.name if isinstance(node, exp.Column) else None


def _describe_predicate(pred: exp.Expression) -> str:
    if isinstance(pred, exp.EQ) and _column(pred.left) and isinstance(pred.right, exp.Literal):
        return f"{readable_name(_column(pred.left) or '')}: {pred.right.name}"
    if isinstance(pred, exp.In) and _column(pred.this):
        values = ", ".join(str(item.name) for item in pred.expressions if isinstance(item, exp.Literal))
        if values:
            return f"{readable_name(_column(pred.this) or '')}: {values}"
    return _ALIAS.sub("", pred.sql(dialect="trino"))


def _period_text(dates: list[date]) -> str | None:
    if not dates:
        return None
    ordered = sorted(dates)
    if len(ordered) >= 2:
        return f"{ordered[0].isoformat()} to {(ordered[-1] - timedelta(days=1)).isoformat()}"
    return ordered[0].isoformat()


def clean_formula(expression: str | None, dataset: str | None = None) -> str | None:
    if not expression:
        return None
    text = _ALIAS.sub("", str(expression))
    if dataset:
        text = text.replace(f"{dataset}.", "")
    return " ".join(text.split())[:300]


def _filters_and_period(sql: str, row_filter: str | None) -> tuple[list[str], str | None, list[str]]:
    tree = _parse(sql)
    if tree is None:
        return [], None, []
    filters: list[str] = []
    dates: list[date] = []
    for pred in _conjuncts(tree.args.get("where")):
        rendered = pred.sql(dialect="trino")
        found = _DATE_LITERAL.findall(rendered)
        if found:
            try:
                dates.extend(date.fromisoformat(value) for value in found)
            except ValueError:
                filters.append(_describe_predicate(pred))
            continue
        if row_filter and _ALIAS.sub("", rendered).strip("() ") == _ALIAS.sub("", row_filter).strip("() "):
            continue  # part of the metric definition, already shown as the formula
        filters.append(_describe_predicate(pred))
    tables = list(dict.fromkeys(table.name for table in tree.find_all(exp.Table) if table.name))
    return filters, _period_text(dates), tables


def _breakdown(sql: str, dims: list[str], dataset: str | None) -> list[str]:
    monthly = "DATE_TRUNC('MONTH'" in sql.upper()
    out = []
    for key in dims:
        label = readable_name(key, dataset)
        if monthly and re.search(r"date|month|period|tanggal|bulan", label, re.I):
            label = f"month of {label}"
        out.append(label)
    return list(dict.fromkeys(out))


def _comparison_text(drill: dict[str, Any], language: str) -> str | None:
    kind = drill.get("kind")
    meta = drill.get("meta") or {}
    indonesian = language == "id"
    if kind == "periods":
        return (
            f"Dua periode dibandingkan: {meta.get('previous')} dan {meta.get('current')}. Tiap periode dihitung terpisah; perubahan = periode kemudian dikurangi periode awal."
            if indonesian
            else f"Two periods compared: {meta.get('previous')} and {meta.get('current')}. Each is computed separately; change = later minus earlier."
        )
    if kind == "benchmark":
        direction = meta.get("direction")
        if direction == "any":
            return (
                "Nilai dibandingkan dengan nilai keseluruhan dari seluruh data; selisih = nilai kelompok dikurangi nilai keseluruhan."
                if indonesian
                else "Compared with the overall value computed over all records; difference = the group's value minus the overall value."
            )
        margin = float(meta.get("margin") or 0)
        extra = f" by more than {margin:g} points" if margin else ""
        return f"Only groups {direction} the overall value{extra} are shown; the overall value is computed over all records."
    if drill.get("queries") and len(drill["queries"]) > 1:
        return (
            "Setiap metrik dihitung terpisah dari definisi governed-nya lalu digabung pada nilai dimensi yang sama."
            if indonesian
            else "Each metric is computed separately from its governed definition and joined on the shared dimension values."
        )
    return None


def build_calculation_note(
    *,
    strategy: str,
    sql: str | None,
    metric: str | None,
    definition: dict[str, Any] | None,
    dimensions: list[str] | None,
    drill: dict[str, Any] | None,
    language: str = "en",
    checks: list[CalculationCheck] | None = None,
) -> CalculationNote | None:
    """None when there is nothing executed to explain (clarifications, conversational turns)."""
    first_sql = ((drill or {}).get("queries") or [{}])[0].get("sql") if drill else None
    sql_text = str(first_sql or sql or "").strip()
    if not sql_text:
        return None
    definition = definition or {}
    dataset = str(definition.get("base_dataset") or "") or None
    filters, period, tables = _filters_and_period(sql_text, definition.get("row_filter"))
    comparison = _comparison_text(drill, language) if drill else None
    if drill and drill.get("kind") == "periods":
        meta = drill.get("meta") or {}
        period = f"{meta.get('previous')} vs {meta.get('current')}"
    dims = list(dimensions or [])
    if drill and drill.get("queries"):
        dims = list(drill["queries"][0].get("dimensions") or dims)
    breakdown = _breakdown(sql_text, dims, dataset)
    is_governed = bool(metric) and strategy == "governed"
    label = humanize_metric_label(name=metric, definition=definition) if metric else None
    formula = clean_formula(definition.get("expression"), dataset) if is_governed else None
    kind = "comparison" if comparison and drill and drill.get("kind") in {"periods", "benchmark"} else ("governed" if is_governed else "fallback")
    parts = [label or "Controlled SQL over approved views"]
    if breakdown:
        parts.append("by " + ", ".join(breakdown))
    if period:
        parts.append(period)
    if filters:
        parts.append(", ".join(filters[:2]) + (f" +{len(filters) - 2} more" if len(filters) > 2 else ""))
    if tables:
        parts.append(", ".join(tables))
    return CalculationNote(
        kind=kind,
        summary=" · ".join(parts),
        metric=label,
        formula=formula,
        breakdown=breakdown,
        filters=filters,
        period=period,
        source=tables,
        comparison=comparison,
        checks=checks or [],
    )

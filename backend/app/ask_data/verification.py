"""Checks run on an executed answer before it is written up: does what ran match what was asked?

The results are shown in "How this was calculated" and every warning is also handed to the analyst as a caveat, so
an answer that does not fully match the question says so instead of sounding sure.
"""
from __future__ import annotations

import re
from typing import Any

from app.ask_data.comparisons import find_periods
from app.ask_data.intent_satisfaction import parse_requested_constraints
from app.core.models import CalculationCheck

_DATE_IN_SQL = re.compile(r"(?:DATE|TIMESTAMP)\s*'\d{4}-\d{2}-\d{2}|CAST\(\s*'\d{4}-\d{2}-\d{2}", re.I)
_MONTH_GROUP = re.compile(r"DATE_TRUNC\(\s*'month'", re.I)


def _numbers(rows: list[dict[str, Any]], column: str) -> list[float]:
    out: list[float] = []
    for row in rows:
        value = row.get(column)
        if isinstance(value, bool) or value is None:
            continue
        try:
            out.append(float(value))
        except (TypeError, ValueError):
            continue
    return out


def _is_percentage(definition: dict[str, Any]) -> bool:
    unit = str(definition.get("unit_format") or "").casefold()
    expression = str(definition.get("expression") or "")
    return "percent" in unit or "%" in unit or bool(re.search(r"\*\s*100(?:\.0+)?\b", expression))


def verify_answer(
    *,
    question: str,
    sql: str,
    columns: list[str],
    rows: list[dict[str, Any]],
    definition: dict[str, Any] | None,
    drill: dict[str, Any] | None,
    truncated: bool = False,
) -> list[CalculationCheck]:
    """Only the checks that apply to this question; an ordinary question may return an empty list."""
    checks: list[CalculationCheck] = []
    constraints = parse_requested_constraints(question)
    kind = (drill or {}).get("kind")
    sql_text = sql or ""

    period = constraints.explicit_range
    if period is not None and kind != "periods":
        if _DATE_IN_SQL.search(sql_text):
            checks.append(CalculationCheck(name="period", status="ok", message=f"The period asked for ({period.label}) is applied as a date filter."))
        else:
            checks.append(CalculationCheck(name="period", status="warning", message=f"The question names {period.label} but the query has no date filter, so the figures cover every date."))
    elif kind == "periods":
        checks.append(CalculationCheck(name="period", status="ok", message="Both periods were computed separately and merged."))
    elif kind != "benchmark":
        # Months named without a year ("between March and June") still have to show up as a date filter.
        named = find_periods(question)
        if named:
            label = named[0][2].label
            if _DATE_IN_SQL.search(sql_text):
                checks.append(CalculationCheck(name="period", status="ok", message=f"The period asked for ({label}) is applied as a date filter."))
            else:
                checks.append(CalculationCheck(name="period", status="warning", message=f"The question names {label} but the query has no date filter, so the figures cover every date."))

    if "time_month" in constraints.requested_grouping:
        if _MONTH_GROUP.search(sql_text):
            checks.append(CalculationCheck(name="grouping", status="ok", message="The result is split by month, in date order."))
        else:
            checks.append(CalculationCheck(name="grouping", status="warning", message="The question asks for a monthly breakdown but the result is not split by month."))

    if definition and rows and _is_percentage(definition):
        metric_columns = [c for c in columns if c in {"metric_value", "overall_value"}] or ["metric_value"]
        values = [v for column in metric_columns for v in _numbers(rows, column)]
        if values and (min(values) < 0 or max(values) > 100):
            checks.append(CalculationCheck(name="range", status="warning", message=f"A percentage metric returned values from {min(values):g} to {max(values):g}, outside 0 to 100."))
        elif values:
            checks.append(CalculationCheck(name="range", status="ok", message="Percentage values stay between 0 and 100."))

    if truncated:
        checks.append(CalculationCheck(name="rows", status="warning", message="The result was cut at the row limit; narrow the question to see everything."))
    return checks


def warning_messages(checks: list[CalculationCheck]) -> list[str]:
    return [check.message for check in checks if check.status == "warning"]

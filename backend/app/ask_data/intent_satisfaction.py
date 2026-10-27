"""Deterministic business-intent checks for registry (UAT) semantic runtime."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

_MONTH_TERMS: tuple[tuple[tuple[str, ...], int], ...] = (
    (("januari", "january", " jan "), 1),
    (("februari", "february", " feb "), 2),
    (("maret", "march", " mar "), 3),
    (("april", " apr "), 4),
    (("mei", "may"), 5),
    (("juni", "june", " jun "), 6),
    (("juli", "july", " jul "), 7),
    (("agustus", "august", " aug "), 8),
    (("september", " sep "), 9),
    (("oktober", "october", " okt ", " oct "), 10),
    (("november", " nov "), 11),
    (("desember", "december", " dec ", " des "), 12),
)

# Business concepts not satisfied by metric-only aggregation when absent from the model.
_CONCEPT_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\b(region|regional|antarctica|antarctic|geo(?:graphic)?)\b", re.I), "region"),
    (re.compile(r"\b(satisfaction|nps|csat|customer\s+satisfaction)\b", re.I), "customer_satisfaction"),
    (re.compile(r"\b(by\s+store|per\s+store|store\s+level)\b", re.I), "store"),
)

# Map requested concept → allowed dimension keys that would satisfy it.
_CONCEPT_TO_DIMENSION_KEYS: dict[str, frozenset[str]] = {
    "region": frozenset({"region", "sales_region", "customer_region"}),
    "store": frozenset({"store", "store_id", "store_name"}),
    "customer_satisfaction": frozenset(),  # never satisfied by sales facts alone
}


@dataclass(frozen=True)
class CalendarPeriod:
    year: int
    month: int


@dataclass
class IntentConstraints:
    requested_concepts: list[str] = field(default_factory=list)
    explicit_period: CalendarPeriod | None = None
    requested_grouping: list[str] = field(default_factory=list)


@dataclass
class IntentValidation:
    intent_complete: bool
    requested_constraints: dict[str, Any]
    resolved_constraints: dict[str, Any]
    unresolved_constraints: list[str]
    user_message: str = ""
    reason_code: str = ""

    def as_metadata(self) -> dict[str, Any]:
        return {
            "intent_complete": self.intent_complete,
            "requested_constraints": self.requested_constraints,
            "resolved_constraints": self.resolved_constraints,
            "unresolved_constraints": self.unresolved_constraints,
            "reason_code": self.reason_code or None,
        }


def parse_explicit_calendar_period(question: str) -> CalendarPeriod | None:
    lowered = f" {question.casefold()} "
    year_match = re.search(r"\b(20\d{2})\b", lowered)
    year = int(year_match.group(1)) if year_match else None
    month: int | None = None
    for terms, idx in _MONTH_TERMS:
        if any(term in lowered for term in terms):
            month = idx
            break
    if month is None:
        return None
    if year is None:
        # Explicit month without year — only accept when question still anchors a calendar year elsewhere
        # or uses phrasing like "May 2024" handled above; otherwise require clarification upstream.
        return None
    return CalendarPeriod(year=year, month=month)


def parse_requested_constraints(question: str) -> IntentConstraints:
    constraints = IntentConstraints()
    for pattern, concept in _CONCEPT_PATTERNS:
        if pattern.search(question):
            constraints.requested_concepts.append(concept)
    constraints.requested_concepts = list(dict.fromkeys(constraints.requested_concepts))
    period = parse_explicit_calendar_period(question)
    if period:
        constraints.explicit_period = period
    lowered = question.casefold()
    if any(t in lowered for t in ("by month", "per month", "by month", "monthly", "per bulan", "per bulan")):
        constraints.requested_grouping.append("time_month")
    return constraints


def _allowed_dimension_keys(definition: dict[str, Any]) -> set[str]:
    return set(definition.get("allowed_dimensions") or [])


def _time_dimension_keys(dataset_name: str, registry: Any) -> list[str]:
    fields = registry.dataset_fields.get(dataset_name, {})
    keys: list[str] = []
    for dim_key, field in fields.items():
        if (field.get("dimension") or {}).get("is_time"):
            keys.append(dim_key)
        elif dim_key in ("sale_date", "sale_month", "reporting_period", "calmonth"):
            keys.append(dim_key)
    return keys


def validate_registry_resolution(
    question: str,
    resolution: dict[str, Any],
    *,
    definition: dict[str, Any],
    registry: Any,
) -> IntentValidation:
    requested = parse_requested_constraints(question)
    allowed = _allowed_dimension_keys(definition)
    dataset_name = str(definition.get("base_dataset") or "")
    time_dims = _time_dimension_keys(dataset_name, registry)
    resolved_dims = list(resolution.get("dimensions") or [])
    unresolved: list[str] = []

    for concept in requested.requested_concepts:
        satisfiers = _CONCEPT_TO_DIMENSION_KEYS.get(concept, frozenset())
        if concept == "customer_satisfaction":
            unresolved.append("customer_satisfaction")
            continue
        if not satisfiers & allowed:
            unresolved.append(concept)

    resolved_period = requested.explicit_period is not None and bool(time_dims)
    if requested.explicit_period and not time_dims:
        unresolved.append("time_period")

    validation = IntentValidation(
        intent_complete=not unresolved,
        requested_constraints={
            "concepts": requested.requested_concepts,
            "explicit_period": (
                {"year": requested.explicit_period.year, "month": requested.explicit_period.month}
                if requested.explicit_period
                else None
            ),
            "grouping": requested.requested_grouping,
        },
        resolved_constraints={
            "metric": resolution.get("metric"),
            "dimensions": resolved_dims,
            "allowed_dimensions": sorted(allowed),
            "time_dimensions_available": time_dims,
            "explicit_period_resolvable": resolved_period,
        },
        unresolved_constraints=unresolved,
    )

    if "region" in unresolved:
        validation.reason_code = "UNSUPPORTED_DIMENSION"
        validation.user_message = (
            "I can calculate total sales from the active semantic model, but it does not include "
            "a region or geography dimension. I cannot answer a regional breakdown or filter such as Antarctica."
        )
    elif "customer_satisfaction" in unresolved or "store" in unresolved:
        validation.reason_code = "INSUFFICIENT_CONTEXT"
        concept = "customer satisfaction" if "customer_satisfaction" in unresolved else "store"
        validation.user_message = (
            f"The current semantic model does not expose the {concept} context needed to answer this question. "
            "Please ask about metrics and dimensions that are configured in the semantic layer."
        )
    elif "time_period" in unresolved:
        validation.reason_code = "INSUFFICIENT_CONTEXT"
        validation.user_message = (
            "This question asks for a specific time period, but the active semantic model does not expose "
            "a governed date field to filter on."
        )
    validation.intent_complete = not unresolved
    return validation


def registry_period_sql_predicate(
    question: str,
    *,
    dataset_name: str,
    registry: Any,
) -> str | None:
    period = parse_explicit_calendar_period(question)
    if not period:
        return None
    time_keys = _time_dimension_keys(dataset_name, registry)
    if not time_keys:
        return None
    dim_key = time_keys[0]
    fields = registry.dataset_fields.get(dataset_name, {})
    field = fields.get(dim_key)
    if not field:
        return None
    expr = registry.ansi_expression(field)
    expr = expr.replace(f"{dataset_name}.", "d.")
    if not re.match(r"^d\.", expr.strip(), flags=re.I):
        expr = f"d.{expr}"
    y, m = period.year, period.month
    start = f"{y:04d}-{m:02d}-01"
    end_year, end_month = (y + 1, 1) if m == 12 else (y, m + 1)
    end = f"{end_year:04d}-{end_month:02d}-01"
    return f"({expr} >= DATE '{start}' AND {expr} < DATE '{end}')"


def validate_governed_sql_covers_intent(
    question: str,
    sql: str,
    *,
    definition: dict[str, Any],
    registry: Any,
) -> IntentValidation:
    """Post-compile check: explicit calendar period must appear in SQL when requested."""
    base = validate_registry_resolution(
        question,
        {"status": "resolved", "metric": definition.get("metric"), "dimensions": []},
        definition=definition,
        registry=registry,
    )
    period = parse_explicit_calendar_period(question)
    if not period or base.unresolved_constraints:
        return base
    lowered_sql = sql.casefold()
    month_token = f"{period.year:04d}-{period.month:02d}"
    has_period = month_token in lowered_sql or f"date '{month_token}" in lowered_sql
    if not has_period:
        base.intent_complete = False
        base.unresolved_constraints = list(dict.fromkeys([*base.unresolved_constraints, "time_filter_missing"]))
        base.reason_code = "INCOMPLETE_PLAN"
        base.user_message = (
            f"The question asks for a specific period ({month_token}), but the generated query "
            "did not apply the required date filter."
        )
    base.resolved_constraints["sql_has_period_filter"] = has_period
    return base

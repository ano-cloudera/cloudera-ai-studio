"""Lightweight metric draft validation for authoring UX."""
from __future__ import annotations

import re
from dataclasses import dataclass

from app.semantic_registry.metric_metadata import related_entity_keys

_AGG_NUMERIC = frozenset({"sum", "avg", "average", "min", "max"})
_AGG_ANY = frozenset({"count", "count_distinct", "count distinct"})
_SIMPLE_AGG_RE = re.compile(
    r"^(?P<fn>SUM|COUNT|AVG|MIN|MAX)\(\s*(?P<col>[a-zA-Z_][a-zA-Z0-9_]*)\s*\)$",
    re.IGNORECASE,
)
_COUNT_DISTINCT_RE = re.compile(
    r"^COUNT\s*\(\s*DISTINCT\s+(?P<col>[a-zA-Z_][a-zA-Z0-9_]*)\s*\)$",
    re.IGNORECASE,
)


@dataclass
class MetricFieldIssue:
    field: str
    message: str


@dataclass
class MetricValidationResult:
    valid: bool
    issues: list[MetricFieldIssue]
    form_message: str | None = None


def _column_types_for_entity(
    entity_key: str,
    dimensions,
    entity_metadata: dict | None = None,
) -> dict[str, str]:
    out: dict[str, str] = {}
    # The physical column type is the source of truth; a dimension's declared type may be a loose guess
    # (a numeric measure such as decision_time_hours can be listed as a "string" dimension).
    if entity_metadata:
        for col in entity_metadata.get("physical_columns") or []:
            if not isinstance(col, dict):
                continue
            name = str(col.get("name") or "").strip()
            physical = str(col.get("normalized_type") or "").strip().lower()
            if name and physical and physical != "unknown":
                out[name] = physical
    for d in dimensions:
        if d.source_entity_key == entity_key and d.source_column:
            out.setdefault(d.source_column, (d.data_type or "string").lower())
    if entity_metadata:
        for col in entity_metadata.get("physical_columns") or []:
            if isinstance(col, dict) and str(col.get("name") or "").strip():
                out.setdefault(str(col["name"]).strip(), "string")
    return out


def _is_numeric_type(data_type: str) -> bool:
    t = data_type.lower()
    return any(x in t for x in ("int", "decimal", "numeric", "float", "double", "number", "real"))


def validate_metric_draft(
    *,
    name: str,
    business_definition: str | None,
    expression: str,
    aggregation: str | None,
    source_entity_key: str,
    entity_keys: set[str],
    dimensions,
    existing_metric_names: set[str],
    metric_id: str | None = None,
    require_definition: bool = True,
    allowed_dimension_keys: list[str] | None = None,
    relationships=None,
    source_entity_metadata: dict | None = None,
) -> MetricValidationResult:
    issues: list[MetricFieldIssue] = []
    if not name.strip():
        issues.append(MetricFieldIssue("name", "Metric name is required."))
    if require_definition and not (business_definition or "").strip():
        issues.append(MetricFieldIssue("business_definition", "Business definition is required."))
    if not source_entity_key or source_entity_key not in entity_keys:
        issues.append(MetricFieldIssue("source_entity_key", "Select a valid data model."))
    norm_name = name.strip().casefold()
    if norm_name in existing_metric_names:
        issues.append(MetricFieldIssue("name", f"A metric named `{name}` already exists."))
    expr = (expression or "").strip()
    if not expr:
        issues.append(MetricFieldIssue("expression", "Calculation expression is required."))
        return MetricValidationResult(valid=False, issues=issues, form_message=issues[0].message if issues else None)

    col_types = _column_types_for_entity(source_entity_key, dimensions, source_entity_metadata)
    agg = (aggregation or "").strip().lower()

    m = _COUNT_DISTINCT_RE.match(expr)
    if m:
        col = m.group("col")
        if col not in col_types:
            issues.append(MetricFieldIssue("expression", f"Column `{col}` was not found in {source_entity_key}."))
    else:
        m2 = _SIMPLE_AGG_RE.match(expr)
        if m2 and agg != "formula":
            col = m2.group("col")
            fn = m2.group("fn").lower()
            if col not in col_types:
                issues.append(
                    MetricFieldIssue("expression", f"Column `{col}` was not found in {source_entity_key}.")
                )
            elif fn in ("sum", "avg", "min", "max") and col in col_types and not _is_numeric_type(col_types[col]):
                issues.append(
                    MetricFieldIssue(
                        "expression",
                        f"`{col}` cannot be used with {fn.upper()} (expected a numeric column).",
                    )
                )
        elif agg != "formula" and agg in _AGG_NUMERIC.union(_AGG_ANY):
            pass
        elif not m2:
            if re.search(r"\b(DROP|DELETE|INSERT|UPDATE|ALTER|TRUNCATE)\b", expr, re.I):
                issues.append(MetricFieldIssue("expression", "Formula contains disallowed SQL statements."))
            elif len(expr) < 2:
                issues.append(MetricFieldIssue("expression", "Formula could not be parsed."))

    if allowed_dimension_keys and source_entity_key in entity_keys:
        related = related_entity_keys(source_entity_key, relationships or [])
        dim_by_key = {d.key: d for d in dimensions}
        for key in allowed_dimension_keys:
            k = str(key).strip()
            if not k:
                continue
            dim = dim_by_key.get(k)
            if dim is None or dim.source_entity_key not in related:
                issues.append(
                    MetricFieldIssue(
                        "allowed_dimension_keys",
                        f"Dimension `{k}` is not available for this metric's data model.",
                    )
                )

    valid = not issues
    summary = issues[0].message if len(issues) == 1 else (f"{len(issues)} validation issues" if issues else None)
    return MetricValidationResult(valid=valid, issues=issues, form_message=summary)

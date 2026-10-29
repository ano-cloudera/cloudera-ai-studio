"""Deterministic business-intent checks for registry (UAT) semantic runtime."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
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

_MONTH_WORDS: dict[str, int] = {
    "january": 1, "jan": 1, "januari": 1,
    "february": 2, "feb": 2, "februari": 2,
    "march": 3, "mar": 3, "maret": 3,
    "april": 4, "apr": 4,
    "may": 5, "mei": 5,
    "june": 6, "jun": 6, "juni": 6,
    "july": 7, "jul": 7, "juli": 7,
    "august": 8, "aug": 8, "agustus": 8, "agu": 8,
    "september": 9, "sep": 9, "sept": 9,
    "october": 10, "oct": 10, "oktober": 10, "okt": 10,
    "november": 11, "nov": 11,
    "december": 12, "dec": 12, "desember": 12, "des": 12,
}
_MONTH_RE = "|".join(sorted(_MONTH_WORDS, key=len, reverse=True))
_YEAR_RE = r"20\d{2}"
_RANGE_JOINER = r"(?:to|through|thru|until|till|and|sampai|hingga|dan|s/d|-|\u2013)"
_QUARTER_PATTERNS = (
    re.compile(rf"\bq([1-4])\b[\s,/-]*(?:of\s+)?({_YEAR_RE})", re.I),
    re.compile(rf"\b({_YEAR_RE})[\s,/-]*q([1-4])\b", re.I),
    re.compile(rf"\b(?:quarter|kuartal|triwulan)\s*([1-4])\s*(?:of\s+)?({_YEAR_RE})", re.I),
)
_RANGE_PATTERN = re.compile(
    rf"\b(?P<m1>{_MONTH_RE})\b(?:\s+(?P<y1>{_YEAR_RE}))?\s*{_RANGE_JOINER}\s*(?P<m2>{_MONTH_RE})\b\s*(?P<y2>{_YEAR_RE})?",
    re.I,
)
_SINGLE_MONTH_PATTERN = re.compile(rf"\b(?P<m>{_MONTH_RE})\b[\s,]*(?P<y>{_YEAR_RE})\b", re.I)
_YEAR_PATTERN = re.compile(rf"\b(?:in|during|for|pada|tahun|year|throughout)\s+({_YEAR_RE})\b", re.I)


@dataclass(frozen=True)
class PeriodRange:
    start: date
    end: date  # exclusive
    label: str

    def is_single_month(self) -> bool:
        return self.start.day == 1 and self.end == _month_start(self.start.year, self.start.month + 1)


def _month_start(year: int, month: int) -> date:
    year += (month - 1) // 12
    month = (month - 1) % 12 + 1
    return date(year, month, 1)


def parse_period_range(question: str) -> PeriodRange | None:
    """A calendar quarter, month range ("June to August 2026"), single month with year, or whole year."""
    text = question or ""
    for index, pattern in enumerate(_QUARTER_PATTERNS):
        match = pattern.search(text)
        if match:
            first, second = match.group(1), match.group(2)
            quarter, year = (int(first), int(second)) if index != 1 else (int(second), int(first))
            start = _month_start(year, (quarter - 1) * 3 + 1)
            return PeriodRange(start, _month_start(year, (quarter - 1) * 3 + 4), f"Q{quarter} {year}")
    match = _RANGE_PATTERN.search(text)
    if match:
        year = match.group("y2") or match.group("y1")
        first_year = match.group("y1") or year
        if year:
            m1, m2 = _MONTH_WORDS[match.group("m1").casefold()], _MONTH_WORDS[match.group("m2").casefold()]
            start = _month_start(int(first_year), m1)
            end = _month_start(int(year), m2 + 1)
            if start < end:
                return PeriodRange(start, end, f"{start:%Y-%m} to {_month_start(int(year), m2):%Y-%m}")
    match = _SINGLE_MONTH_PATTERN.search(text)
    if match:
        month, year = _MONTH_WORDS[match.group("m").casefold()], int(match.group("y"))
        return PeriodRange(_month_start(year, month), _month_start(year, month + 1), f"{year:04d}-{month:02d}")
    match = _YEAR_PATTERN.search(text)
    if match:
        year = int(match.group(1))
        return PeriodRange(date(year, 1, 1), date(year + 1, 1, 1), str(year))
    return None


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
    explicit_range: PeriodRange | None = None
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
    """A single calendar month with a year; ranges, quarters and years go through `parse_period_range`."""
    period = parse_period_range(question)
    if period is None or not period.is_single_month():
        return None
    return CalendarPeriod(year=period.start.year, month=period.start.month)


def parse_requested_constraints(question: str) -> IntentConstraints:
    constraints = IntentConstraints()
    for pattern, concept in _CONCEPT_PATTERNS:
        if pattern.search(question):
            constraints.requested_concepts.append(concept)
    constraints.requested_concepts = list(dict.fromkeys(constraints.requested_concepts))
    constraints.explicit_range = parse_period_range(question)
    period = parse_explicit_calendar_period(question)
    if period:
        constraints.explicit_period = period
    lowered = question.casefold()
    if any(t in lowered for t in ("by month", "per month", "by month", "monthly", "per bulan", "per bulan")):
        constraints.requested_grouping.append("time_month")
    return constraints


_CONCEPT_DIMENSION_NAME = {
    "region": re.compile(r"region|geo|province|provinsi|wilayah|area|city|kota", re.I),
    "store": re.compile(r"store|toko|outlet", re.I),
}


def _concept_satisfied(concept: str, allowed: set[str]) -> bool:
    if allowed & _CONCEPT_TO_DIMENSION_KEYS.get(concept, frozenset()):
        return True
    pattern = _CONCEPT_DIMENSION_NAME.get(concept)
    return bool(pattern and any(pattern.search(key) for key in allowed))


def _allowed_dimension_keys(definition: dict[str, Any]) -> set[str]:
    return set(definition.get("allowed_dimensions") or [])


def _time_dimension_keys(dataset_name: str, registry: Any) -> list[str]:
    fields = registry.dataset_fields.get(dataset_name, {})
    keys: list[str] = []
    for dim_key, field in fields.items():
        if (field.get("dimension") or {}).get("is_time"):
            keys.append(dim_key)
        elif dim_key in ("sale_date", "sale_month", "reporting_period", "calmonth") or re.search(
            r"(?:^|_)(?:date|month|period)$", dim_key
        ):
            keys.append(dim_key)
    return keys


_BREAKDOWN_PHRASE = re.compile(
    r"\b(?:by|per|across|for\s+each|each|grouped\s+by|broken\s+down\s+by|breakdown\s+by|berdasarkan)\s+"
    r"(?P<phrase>.+?)(?=\s+(?:from|in|during|between|for|where|with|that|which|over|sampai|dari|selama|pada)\b|[?.;!]|$)",
    re.I,
)
_WHICH_PHRASE = re.compile(
    r"\b(?:which|what|who)\s+(?P<phrase>[a-z_ ]+?)\s+(?:has|have|had|is|are|was|were|with)\s+the\s+"
    r"(?:highest|lowest|most|least|top|bottom|largest|smallest|best|worst|fewest)\b",
    re.I,
)
_ASCENDING_RANK = re.compile(
    r"\b(lowest|least|bottom|smallest|fewest|worst|terendah|terkecil|paling\s+sedikit)\b", re.I
)
_GENERIC_DIMENSION_WORDS = frozenset(
    {"id", "name", "code", "key", "flag", "application", "applications", "customer", "credit", "loan", "status",
     "amount", "value", "number", "date"}
)
_DIMENSION_WORD_SYNONYMS: dict[str, frozenset[str]] = {
    "region": frozenset({"wilayah", "provinsi", "area"}),
    "channel": frozenset({"saluran", "kanal"}),
    "segment": frozenset({"segmen"}),
    "product": frozenset({"produk"}),
    "category": frozenset({"kategori"}),
}


def requested_sort_direction(question: str) -> str:
    """ASC when the question asks for the lowest/least, otherwise DESC."""
    return "ASC" if _ASCENDING_RANK.search(question or "") else "DESC"


def _dimension_words(key: str, dataset_name: str) -> list[str]:
    base = key[len(dataset_name) + 1 :] if key.startswith(f"{dataset_name}_") else key
    words = [w for w in base.casefold().split("_") if w and w not in _GENERIC_DIMENSION_WORDS]
    # "decision_status" keeps its distinctive word even though "status" alone is generic.
    return words or [w for w in base.casefold().split("_") if w and w not in {"id", "flag"}]


def infer_dimensions_from_question(
    question: str,
    allowed: set[str],
    *,
    dataset_name: str,
    registry: Any,
) -> list[str]:
    """Breakdown dimensions named after "by", "per", "across" or "which <dimension> has the highest"."""
    phrases = [m.group("phrase") for m in _BREAKDOWN_PHRASE.finditer(question or "")]
    phrases += [m.group("phrase") for m in _WHICH_PHRASE.finditer(question or "")]
    if not phrases:
        return []
    time_keys = set(_time_dimension_keys(dataset_name, registry))
    found: list[tuple[int, str]] = []
    for key in sorted(allowed):
        if key in time_keys or key.endswith(("_id", "_flag")):
            continue
        words = _dimension_words(key, dataset_name)
        candidates = {w for word in words for w in (word, *_DIMENSION_WORD_SYNONYMS.get(word, ()))}
        for phrase in phrases:
            lowered = phrase.casefold()
            hits = [m.start() for w in candidates for m in re.finditer(rf"\b{re.escape(w)}\b", lowered)]
            if hits:
                found.append((min(hits), key))
                break
    return [key for _, key in sorted(found)]


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
        if concept == "customer_satisfaction":
            unresolved.append("customer_satisfaction")
            continue
        if not _concept_satisfied(concept, allowed):
            unresolved.append(concept)

    resolved_period = requested.explicit_range is not None and bool(time_dims)
    if requested.explicit_range and not time_dims:
        unresolved.append("time_period")

    validation = IntentValidation(
        intent_complete=not unresolved,
        requested_constraints={
            "concepts": requested.requested_concepts,
            "explicit_period": (
                {"start": requested.explicit_range.start.isoformat(), "end": requested.explicit_range.end.isoformat()}
                if requested.explicit_range
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
        metric_label = str(resolution.get("metric") or "this metric").replace("_", " ")
        dims = ", ".join(sorted(k.replace("_", " ") for k in allowed)[:8])
        validation.user_message = (
            f"I can calculate {metric_label} from the active semantic model, but it does not include "
            "a region or geography dimension, so I cannot answer a regional breakdown or filter."
            + (f" Available dimensions: {dims}." if dims else "")
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
    period = parse_period_range(question)
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
    return f"({expr} >= DATE '{period.start.isoformat()}' AND {expr} < DATE '{period.end.isoformat()}')"


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
    period = parse_period_range(question)
    if not period or base.unresolved_constraints:
        return base
    lowered_sql = sql.casefold()
    start_token = period.start.isoformat()
    has_period = start_token in lowered_sql
    if not has_period:
        base.intent_complete = False
        base.unresolved_constraints = list(dict.fromkeys([*base.unresolved_constraints, "time_filter_missing"]))
        base.reason_code = "INCOMPLETE_PLAN"
        base.user_message = (
            f"The question asks for a specific period ({period.label}), but the generated query "
            "did not apply the required date filter."
        )
    base.resolved_constraints["sql_has_period_filter"] = has_period
    return base

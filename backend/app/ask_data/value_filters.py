"""Turn dimension values named in a question ("Jawa Barat", "Digital") into governed WHERE predicates.

The values come from the data itself (a cached `SELECT DISTINCT` per low-cardinality text column), so nothing is
guessed: a word becomes a filter only when it is exactly one of the column's values. Columns used by the metric
formula, identifiers and high-cardinality columns are never filtered. The filters are reported back so the answer
can state its scope.
"""
from __future__ import annotations

import inspect
import logging
import re
import time
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any

logger = logging.getLogger(__name__)

MAX_DISTINCT = 200
CACHE_TTL_SECONDS = 600.0
_TEXT_TYPES = {"string", "text", "varchar", "char"}
_CACHE: dict[tuple[str, str], tuple[float, list[str] | None]] = {}

# A misspelt value ("stumatra udtara") is applied only when it is clearly closest to one value, and said so;
# a weaker or tied match is offered back as a question instead of being guessed.
FUZZY_APPLY = 0.85
FUZZY_SUGGEST = 0.70
FUZZY_MARGIN = 0.08
FUZZY_MIN_LENGTH = 5


@dataclass(frozen=True)
class ValueFilter:
    dimension: str
    expression: str
    values: tuple[str, ...]

    def predicate(self) -> str:
        quoted = ", ".join("'" + v.replace("'", "''") + "'" for v in self.values)
        if len(self.values) == 1:
            return f"{self.expression} = {quoted}"
        return f"{self.expression} IN ({quoted})"

    def describe(self, label: str | None = None) -> str:
        return f"{label or self.dimension}: {' or '.join(self.values)}"


def _normalize(text: str) -> str:
    return " ".join(text.casefold().replace("–", "-").split())


def match_values(question: str, catalog: dict[str, list[str]]) -> dict[str, list[str]]:
    """Dimension -> values of that dimension that the question names as whole words. Ambiguous values are dropped."""
    text = _normalize(question)
    found: dict[str, list[str]] = {}
    owners: dict[str, set[str]] = {}
    for dimension, values in catalog.items():
        for value in values:
            norm = _normalize(str(value))
            if len(norm) < 2 or norm.isdigit():
                continue
            if re.search(rf"(?<![a-z0-9]){re.escape(norm)}(?![a-z0-9])", text):
                found.setdefault(dimension, []).append(str(value))
                owners.setdefault(norm, set()).add(dimension)
    ambiguous = {norm for norm, dims in owners.items() if len(dims) > 1}
    cleaned: dict[str, list[str]] = {}
    for dimension, values in found.items():
        kept = [v for v in values if _normalize(v) not in ambiguous]
        # "Jawa" must not also match inside "Jawa Barat": keep only the longest value for overlapping names.
        kept = [v for v in kept if not any(v != o and _normalize(v) in _normalize(o) for o in kept)]
        if kept:
            cleaned[dimension] = kept
    return cleaned


@dataclass(frozen=True)
class FuzzyMatch:
    dimension: str
    heard: str
    values: tuple[str, ...]  # one value when applied, the tied candidates when only suggested
    score: float
    applied: bool


@dataclass
class ValueResolution:
    filters: list[ValueFilter] = field(default_factory=list)
    corrections: list[tuple[str, str]] = field(default_factory=list)  # (heard, value) for applied fuzzy matches
    suggestions: list[tuple[str, tuple[str, ...]]] = field(default_factory=list)  # (heard, candidate values)


def _compact(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", _normalize(text))


# Everyday words of a question. A phrase made only of these is never read as a misspelt value.
_EVERYDAY = frozenset(
    """
    yang dan atau di ke dari untuk pada dengan ini itu kita kami saya anda kamu mereka ada adalah akan sudah belum bisa
    bantu tolong mohon berapa banyak jumlah total semua setiap per apa mana siapa kapan kenapa mengapa bagaimana gimana
    kalau kalo jika tampilkan tunjukkan keluarkan lihat cari hitung buat kirim dikirim kirimkan terima diterima jual beli
    paket barang pesanan order bulan tahun minggu hari ini lalu depan terakhir tertinggi terendah paling lebih kurang
    naik turun tren data nilai rata the a an of for with and or in on at to from by is are was were be can could would
    please show give list how many much what which who when why where per each all total number count value rate
    highest lowest top last this next month year week day
    """.split()
)


def fuzzy_matches(
    question: str,
    catalog: dict[str, list[str]],
    exact: dict[str, list[str]],
    ignore_words: set[str] | None = None,
) -> list[FuzzyMatch]:
    """Values the question names with a typo. Words already matched exactly, and the words of the model itself
    (its table, columns and metric formula), are left alone: "delivery" in a question about delivery is not a typo."""
    words = re.findall(r"[a-z0-9]+", _normalize(question))
    taken = {w for values in exact.values() for value in values for w in re.findall(r"[a-z0-9]+", _normalize(value))}
    vocabulary = {w.casefold() for w in ignore_words or ()}
    taken |= vocabulary
    # A misspelt word of the model's own vocabulary ("deliveray" for "delivery") is not a value either.
    taken |= {
        w for w in words
        if len(w) >= FUZZY_MIN_LENGTH and any(SequenceMatcher(None, w, v).ratio() >= FUZZY_APPLY for v in vocabulary if len(v) >= FUZZY_MIN_LENGTH)
    }
    windows: list[tuple[str, str]] = []
    for size in (1, 2, 3):
        for start in range(len(words) - size + 1):
            chunk = words[start : start + size]
            if any(w in taken for w in chunk):
                continue
            if all(w in _EVERYDAY for w in chunk):
                continue  # "kita kirim" is a sentence, not a misspelt "KilatKirim"
            joined = "".join(chunk)
            if len(joined) >= FUZZY_MIN_LENGTH:
                windows.append((" ".join(chunk), joined))
    out: dict[tuple[str, str], FuzzyMatch] = {}
    for dimension, values in catalog.items():
        known = {_compact(v): str(v) for v in values if len(_compact(v)) >= FUZZY_MIN_LENGTH and not _compact(v).isdigit()}
        exact_here = {_compact(v) for v in exact.get(dimension, [])}
        for heard, joined in windows:
            scored = sorted(
                ((SequenceMatcher(None, joined, key).ratio(), key) for key in known if key not in exact_here),
                reverse=True,
            )
            if not scored or scored[0][0] < FUZZY_SUGGEST:
                continue
            best, best_key = scored[0]
            second = scored[1][0] if len(scored) > 1 else 0.0
            if best >= FUZZY_APPLY and best - second >= FUZZY_MARGIN:
                match = FuzzyMatch(dimension, heard, (known[best_key],), round(best, 2), True)
            else:
                near = tuple(known[key] for score, key in scored if best - score < FUZZY_MARGIN)
                match = FuzzyMatch(dimension, heard, near, round(best, 2), False)
            old = out.get((dimension, match.values[0]))
            if old is None or match.score > old.score:
                out[(dimension, match.values[0])] = match
    matches = list(out.values())
    applied_words = {w for m in matches if m.applied for w in m.heard.split()}
    # "timur" of an applied "kalimantn timur" must not come back as a suggestion for another region.
    return [m for m in matches if m.applied or not set(m.heard.split()) <= applied_words]


def _candidate_dimensions(registry: Any, dataset_name: str, metric_expression: str, allowed: set[str]) -> list[str]:
    fields = registry.dataset_fields.get(dataset_name, {})
    primary = {str(k).casefold() for k in (registry.datasets.get(dataset_name, {}).get("primary_key") or [])}
    used = metric_expression.casefold()
    out = []
    for key in sorted(allowed):
        field = fields.get(key)
        if not field or str(field.get("datatype") or "").casefold() not in _TEXT_TYPES:
            continue
        if (field.get("dimension") or {}).get("is_time"):
            continue
        physical = registry.ansi_expression(field).strip()
        bare = re.sub(r"^d\.", "", physical, flags=re.IGNORECASE).casefold()
        if bare in primary or bare.endswith("_id") or not re.fullmatch(r"[a-z_][a-z0-9_]*", bare):
            continue
        if re.search(rf"\b{re.escape(bare)}\b", used):
            continue  # a column the metric formula already uses
        out.append(key)
    return out


async def _distinct_values(executor: Any, state: dict[str, Any], source: str, expression: str) -> list[str] | None:
    key = (source, expression)
    cached = _CACHE.get(key)
    if cached and time.monotonic() - cached[0] < CACHE_TTL_SECONDS:
        return cached[1]
    sql = f"SELECT DISTINCT {expression} AS v FROM {source} d WHERE {expression} IS NOT NULL LIMIT {MAX_DISTINCT + 1}"
    try:
        result = executor.execute(sql, state)
        if inspect.isawaitable(result):
            result = await result
        values = [str(row.get("v")) for row in (result.get("rows") or []) if isinstance(row, dict) and row.get("v") is not None]
    except Exception:  # noqa: BLE001 - a failed lookup must never break the question
        logger.warning("value_filter_lookup_failed column=%s", expression)
        return None
    cleaned: list[str] | None = None if len(values) > MAX_DISTINCT else values
    _CACHE[key] = (time.monotonic(), cleaned)
    return cleaned


async def resolve_value_matches(
    *,
    question: str,
    dataset_name: str,
    metric_expression: str,
    allowed_dimensions: set[str],
    from_source: str | None,
    semantic_context: Any,
    executor: Any,
    state: dict[str, Any],
    breakdown_dimensions: set[str] | None = None,
    extra_words: list[str] | None = None,
) -> ValueResolution:
    """`breakdown_dimensions` are the dimensions the question groups by: a value of one of them is only a filter when it is spelt
    exactly, never by guessing a typo ("per tipe SPBU (COCO, CODO, DODO)" compares all three, it does not keep COCO).
    `extra_words` are words of the metric itself (its name and synonyms), which are never a misspelt value ("churn")."""
    if not from_source:
        return ValueResolution()
    registry = semantic_context.registry
    catalog: dict[str, list[str]] = {}
    expressions: dict[str, str] = {}
    for key in _candidate_dimensions(registry, dataset_name, metric_expression, allowed_dimensions):
        expression = semantic_context._registry_dimension_expression(dataset_name, key, question)
        values = await _distinct_values(executor, state, from_source, expression)
        if values:
            catalog[key] = values
            expressions[key] = expression
    exact = match_values(question, catalog)
    chosen = {k: list(v) for k, v in exact.items()}
    resolution = ValueResolution()
    vocabulary = {
        w for text in (dataset_name, metric_expression, *allowed_dimensions, *(extra_words or [])) for w in re.findall(r"[a-z0-9]+", str(text).casefold())
    }
    grouped = breakdown_dimensions or set()
    for match in fuzzy_matches(question, catalog, exact, vocabulary):
        if match.dimension in grouped:
            continue
        if match.applied:
            chosen.setdefault(match.dimension, []).append(match.values[0])
            resolution.corrections.append((match.heard, match.values[0]))
        else:
            resolution.suggestions.append((match.heard, match.values))
    resolution.filters = [
        ValueFilter(dimension=k, expression=expressions[k], values=tuple(dict.fromkeys(v))) for k, v in chosen.items()
    ]
    return resolution


async def resolve_value_filters(**kwargs: Any) -> list[ValueFilter]:
    return (await resolve_value_matches(**kwargs)).filters


def clear_cache() -> None:
    _CACHE.clear()

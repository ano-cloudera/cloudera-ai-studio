"""Checks on what the analyst model wrote, after it wrote it.

The model is told never to invent a number and never to describe the calculation, and it still sometimes does both: an
average that is not the average, or a "How this was calculated" sentence the app already shows in its own block. Both are
caught here from the rows, not from the model's say-so: a figure in the summary has to be in the result or derivable from
it (a sum, an average, a difference, a share), and a leading calculation label is removed.
"""
from __future__ import annotations

import itertools
import re
from decimal import Decimal
from typing import Any

from app.core.models import AnalysisOutput

_LABEL = re.compile(
    r"^\s*(?:how this was calculated|how it was calculated|cara (?:penghitungan|perhitungan|menghitung)|calculation)\s*:\s*[^.\n]*(?:\.|$)\s*",
    re.IGNORECASE,
)
_NUMBER = re.compile(r"(?<![\w.,])\d[\d.,]*\d|(?<![\w.,])\d")
_THOUSANDS_COMMA = re.compile(r"^\d{1,3}(?:,\d{3})+$")
_THOUSANDS_DOT = re.compile(r"^\d{1,3}(?:\.\d{3})+$")
MAX_PAIRWISE_ROWS = 30
_SCALES = (1e3, 1e6, 1e9, 1e12)  # "19,75 miliar" for 19,753,449,000


def strip_calculation_label(text: str) -> str:
    """Drops a leading "How this was calculated: ..." sentence; the app shows that in its own block."""
    return _LABEL.sub("", text or "", count=1).strip()


def _as_float(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float, Decimal)):
        number = float(value)
    elif isinstance(value, str):
        try:
            number = float(value.strip())
        except ValueError:
            return None
    else:
        return None
    return number if number == number and abs(number) != float("inf") else None


def _candidates(token: str) -> tuple[set[float], int]:
    """The values a written number can mean (1,002 and 1.002 are both a thousand in some locales) and its decimals."""
    candidates: set[float] = set()
    decimals = 0
    if "," in token and "." in token:
        last = max(token.rfind(","), token.rfind("."))
        whole, fraction = re.sub(r"[.,]", "", token[:last]), token[last + 1 :]
        candidates.add(float(f"{whole}.{fraction}"))
        decimals = len(fraction)
    elif "," in token:
        if _THOUSANDS_COMMA.match(token):
            candidates.add(float(token.replace(",", "")))
        else:
            whole, _, fraction = token.partition(",")
            candidates.add(float(f"{whole}.{fraction}"))
            decimals = len(fraction)
    elif "." in token:
        whole, _, fraction = token.partition(".")
        candidates.add(float(f"{whole}.{fraction}"))
        decimals = len(fraction)
        if _THOUSANDS_DOT.match(token):
            candidates.add(float(token.replace(".", "")))
    else:
        candidates.add(float(token))
    return candidates, decimals


def _worth_checking(token: str, candidates: set[float], decimals: int) -> bool:
    """Only figures that carry a claim: three or more digits, or a decimal. Small counts and years are left alone."""
    if any(1900 <= c <= 2100 and float(c).is_integer() for c in candidates):
        return False
    digits = len(re.sub(r"\D", "", token.split(",")[0].split(".")[0] if decimals else token))
    return decimals > 0 or digits >= 3


def allowed_figures(rows: list[dict[str, Any]], question: str, extras: list[float] | None = None, *, means: bool = True) -> set[float]:
    """Every figure the answer may state: the cells, and what can be worked out from them. `extras` are figures the answer was
    given besides the rows (the overall value), with the differences and ratios against each cell. `means=False` leaves out the
    average of a column: for a rate or an average metric the mean of the groups is not the overall value, and quoting it as a
    comparison point misleads."""
    columns: dict[str, list[float]] = {}
    for row in rows:
        for key, value in row.items():
            number = _as_float(value)
            if number is not None:
                columns.setdefault(key, []).append(number)
    allowed: set[float] = {float(len(rows))}
    for values in columns.values():
        total = sum(values)
        allowed.update(values)
        allowed.update({total, min(values), max(values)})
        if means:
            allowed.add(total / len(values))
        for number in (*values, total):
            allowed.update(number / scale for scale in _SCALES)
        for extra in extras or []:
            allowed.add(extra)
            if extra:
                allowed.update({total / extra * 100, extra - total})  # what several rows together are of the whole
            for v in values:
                allowed.update({v - extra, extra - v})
                if extra:
                    allowed.update({v / extra, v / extra * 100, (v - extra) / abs(extra) * 100})
        if total:
            allowed.update(v / total * 100 for v in values)
        if len(values) <= MAX_PAIRWISE_ROWS:
            for a, b in itertools.permutations(values, 2):
                allowed.add(a - b)
                if b:
                    allowed.add((a - b) / abs(b) * 100)
                    allowed.add(a / b * 100)
                    allowed.add(a / b)
        allowed.update(values[i] - values[i + 1] for i in range(len(values) - 1))
    for token in _NUMBER.findall(question or ""):
        try:
            allowed.update(_candidates(token)[0])
        except ValueError:
            continue
    return allowed


def computed_figures(rows: list[dict[str, Any]], overall: float | None = None, *, additive: bool = False) -> dict[str, Any]:
    """Comparisons worked out from the rows, so the answer quotes them instead of the model doing the arithmetic (it wrote
    "1.26 times" for 714,496 / 574,904, which is 1.24). `additive` metrics (a sum or a count) also get shares of the whole."""
    values: list[tuple[str, float]] = []
    for row in rows:
        value = _as_float(row.get("metric_value"))
        if value is None:
            continue
        label = " / ".join(str(v) for k, v in row.items() if k != "metric_value" and not isinstance(v, (int, float, Decimal)))
        values.append((label or str(len(values) + 1), value))
    if not values:
        return {}
    ordered = sorted(values, key=lambda item: item[1], reverse=True)
    (top, high), (bottom, low) = ordered[0], ordered[-1]
    out: dict[str, Any] = {"highest": {"group": top, "value": round(high, 4)}, "lowest": {"group": bottom, "value": round(low, 4)}}
    if len(ordered) > 1:
        out["gap_highest_minus_lowest"] = round(high - low, 4)
        if low:
            out["ratio_highest_to_lowest"] = round(high / low, 4)
        if ordered[1][1]:
            out["ratio_highest_to_second"] = {"second": ordered[1][0], "ratio": round(high / ordered[1][1], 4)}
    if overall is not None:
        # Every group, not only the extremes: "the only one below", "both above" and "3 of 8" are counted here, never guessed.
        shown = ordered[:30]
        out["difference_from_overall"] = [{"group": g, "difference": round(v - overall, 4)} for g, v in shown]
        above = [g for g, v in ordered if v > overall]
        below = [g for g, v in ordered if v < overall]
        out["above_overall"] = {"count": len(above), "of": len(ordered), "groups": above[:30]}
        out["below_overall"] = {"count": len(below), "of": len(ordered), "groups": below[:30]}
        if additive and overall:
            total = sum(v for _, v in values)
            if 0 <= total <= overall * 1.0001:
                out["these_rows_share_of_overall_pct"] = round(total / overall * 100, 2)
            out["share_of_overall_pct"] = [{"group": g, "share": round(v / overall * 100, 2)} for g, v in ordered[:5]]
    return out


def is_additive(definition: dict[str, Any] | None) -> bool:
    """A sum or a count adds up across groups; a rate or an average does not."""
    expression = str((definition or {}).get("expression") or "").strip().upper()
    return expression.startswith(("SUM(", "COUNT(")) and "/" not in expression and "AVG(" not in expression


def unverified_figures(texts: list[str], rows: list[dict[str, Any]], question: str = "", extras: list[float] | None = None) -> list[str]:
    """Figures written in the texts that are neither in the rows nor derivable from them."""
    if not rows:
        return []
    return figures_outside(texts, allowed_figures(rows, question, extras))


def figures_outside(texts: list[str], allowed: set[float]) -> list[str]:
    """Figures written in the texts that are in none of the allowed figures (within the rounding they are written with)."""
    found: list[str] = []
    for text in texts:
        for token in _NUMBER.findall(text or ""):
            try:
                candidates, decimals = _candidates(token)
            except ValueError:
                continue
            if not _worth_checking(token, candidates, decimals):
                continue
            tolerance = 0.5 * 10 ** (-decimals) + 1e-9
            if not any(abs(c - a) <= tolerance for c in candidates for a in allowed) and token not in found:
                found.append(token)
    return found


def review_answer(
    analysis: AnalysisOutput,
    *,
    rows: list[dict[str, Any]],
    question: str,
    language: str,
    extra_figures: list[float] | None = None,
) -> tuple[AnalysisOutput, list[str]]:
    """The answer without a calculation label and with a caveat for each figure that cannot be verified."""
    summary = strip_calculation_label(analysis.executive_summary)
    insights = [item for item in (strip_calculation_label(i) for i in analysis.insights) if item]
    detailed = strip_calculation_label(analysis.detailed_analysis) if analysis.detailed_analysis else ""
    bad = unverified_figures([analysis.direct_answer, summary, *insights, detailed], rows, question, extra_figures)
    warnings = [
        (
            f"Angka {token} pada ringkasan tidak ada di hasil dan tidak dapat diturunkan darinya, jadi gunakan dengan hati-hati."
            if language == "id"
            else f"The figure {token} in the summary is not in the result and could not be derived from it, so treat it with care."
        )
        for token in bad
    ]
    caveats = [*analysis.caveats, *[w for w in warnings if w not in analysis.caveats]]
    return analysis.model_copy(update={"executive_summary": summary, "insights": insights, "detailed_analysis": detailed, "caveats": caveats}), warnings

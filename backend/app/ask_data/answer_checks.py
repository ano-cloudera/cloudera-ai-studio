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


def allowed_figures(rows: list[dict[str, Any]], question: str) -> set[float]:
    """Every figure the answer may state: the cells, and what can be worked out from them."""
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
        allowed.update({total, total / len(values), min(values), max(values)})
        if total:
            allowed.update(v / total * 100 for v in values)
        if len(values) <= MAX_PAIRWISE_ROWS:
            for a, b in itertools.permutations(values, 2):
                allowed.add(a - b)
                if b:
                    allowed.add((a - b) / abs(b) * 100)
                    allowed.add(a / b * 100)
        allowed.update(values[i] - values[i + 1] for i in range(len(values) - 1))
    for token in _NUMBER.findall(question or ""):
        try:
            allowed.update(_candidates(token)[0])
        except ValueError:
            continue
    return allowed


def unverified_figures(texts: list[str], rows: list[dict[str, Any]], question: str = "") -> list[str]:
    """Figures written in the texts that are neither in the rows nor derivable from them."""
    if not rows:
        return []
    allowed = allowed_figures(rows, question)
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
) -> tuple[AnalysisOutput, list[str]]:
    """The answer without a calculation label and with a caveat for each figure that cannot be verified."""
    summary = strip_calculation_label(analysis.executive_summary)
    insights = [item for item in (strip_calculation_label(i) for i in analysis.insights) if item]
    bad = unverified_figures([analysis.direct_answer, summary, *insights], rows, question)
    warnings = [
        (
            f"Angka {token} pada ringkasan tidak ada di hasil dan tidak dapat diturunkan darinya, jadi gunakan dengan hati-hati."
            if language == "id"
            else f"The figure {token} in the summary is not in the result and could not be derived from it, so treat it with care."
        )
        for token in bad
    ]
    caveats = [*analysis.caveats, *[w for w in warnings if w not in analysis.caveats]]
    return analysis.model_copy(update={"executive_summary": summary, "insights": insights, "caveats": caveats}), warnings

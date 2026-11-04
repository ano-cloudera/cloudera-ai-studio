"""Read two compared periods out of free wording ("antara maret dan juni", "bulan Maret dengan bulan Juni").

The regex in `comparisons.py` stays the first and cheapest path. Only a question that looks like a period comparison and
that the regex could not read is sent to the model, which returns two months or ranges as data. The result is checked here
(valid months, two different periods, not in the far future) before it is used, so a wrong guess can only lead to a
comparison the user can read in "How this was calculated", never to a made-up period.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import date
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from app.ask_data.comparisons import _COMPARE, PeriodComparison
from app.ask_data.intent_satisfaction import _MONTH_RE, PeriodRange, _month_start

logger = logging.getLogger(__name__)

PROMPT_PATH = Path(__file__).resolve().parents[2] / "prompts" / "period_understanding.md"
_MONTH_WORD = re.compile(rf"\b(?:{_MONTH_RE})\b", re.I)
_PERIOD_WORD = re.compile(r"\b(bulan|month|months|quarter|kuartal|triwulan|semester|q[1-4]|h[12])\b", re.I)
_YEAR = re.compile(r"\b20\d{2}\b")
_STRIP = re.compile(rf"\b(?:{_MONTH_RE}|bulan|month|months|periode|period|20\d{{2}})\b", re.I)
_YM = re.compile(r"^(20\d{2})-(0[1-9]|1[0-2])$")


class PeriodSpec(BaseModel):
    start: str
    end: str


class PeriodUnderstanding(BaseModel):
    compare: bool = False
    periods: list[PeriodSpec] = Field(default_factory=list)


def looks_like_period_comparison(question: str) -> bool:
    """A comparison word plus something that names a month or a period; cheap enough to run on every question."""
    text = question or ""
    return bool(_COMPARE.search(text) and (_MONTH_WORD.search(text) or _PERIOD_WORD.search(text)))


def _period(spec: PeriodSpec, today: date) -> PeriodRange | None:
    first, last = _YM.match(spec.start.strip()), _YM.match(spec.end.strip())
    if not first or not last:
        return None
    (y1, m1), (y2, m2) = (int(first[1]), int(first[2])), (int(last[1]), int(last[2]))
    start, end = _month_start(y1, m1), _month_start(y2, m2 + 1)
    if start >= end or start.year < today.year - 15 or start.year > today.year + 1:
        return None
    label = f"{start:%Y-%m}" if (y1, m1) == (y2, m2) else f"{start:%Y-%m} to {_month_start(y2, m2):%Y-%m}"
    return PeriodRange(start, end, label)


def to_comparison(result: PeriodUnderstanding, question: str, today: date) -> PeriodComparison | None:
    if not result.compare or len(result.periods) != 2:
        return None
    periods = [_period(spec, today) for spec in result.periods]
    if any(p is None for p in periods) or periods[0] == periods[1]:
        return None
    earlier, later = sorted((periods[0], periods[1]), key=lambda p: p.start)  # type: ignore[type-var,arg-type]
    return PeriodComparison(earlier, later, " ".join(_STRIP.sub(" ", question).split()))


async def understand_periods(provider: Any, question: str, today: date | None = None) -> PeriodComparison | None:
    """Two periods for a comparison the regex missed, or None. Never raises: any failure means the normal question."""
    today = today or date.today()
    try:
        payload = {"question": question, "today": today.isoformat()}
        result = await provider.generate_structured(
            [
                {"role": "system", "content": PROMPT_PATH.read_text(encoding="utf-8")},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            PeriodUnderstanding,
            temperature=0.0,
            max_tokens=200,
        )
        return to_comparison(result, question, today)
    except Exception:  # noqa: BLE001 - the model failing must never break the question
        logger.warning("period_understanding_failed")
        return None

from __future__ import annotations

import asyncio
from datetime import date

from app.ask_data.comparisons import detect_period_comparison
from app.ask_data.period_understanding import (
    PeriodSpec,
    PeriodUnderstanding,
    looks_like_period_comparison,
    to_comparison,
    understand_periods,
)

TODAY = date(2026, 11, 4)
QUESTION = "Bisa bantu compare data late delivery di sumatera utara antara maret dan juni"


class Provider:
    def __init__(self, result: PeriodUnderstanding | Exception) -> None:
        self.result, self.calls = result, 0

    async def generate_structured(self, messages, model, **_):
        self.calls += 1
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def _two(a: str, b: str) -> PeriodUnderstanding:
    return PeriodUnderstanding(compare=True, periods=[PeriodSpec(start=a, end=a), PeriodSpec(start=b, end=b)])


def test_the_regex_still_cannot_read_this_but_the_gate_lets_it_through() -> None:
    assert detect_period_comparison(QUESTION) is None
    assert looks_like_period_comparison(QUESTION)
    assert not looks_like_period_comparison("Total orders in March 2026")
    assert not looks_like_period_comparison("Compare carriers by late rate")


def test_two_months_become_a_period_comparison_without_the_month_words() -> None:
    result = asyncio.run(understand_periods(Provider(_two("2026-06", "2026-03")), QUESTION, TODAY))
    assert result is not None
    assert (result.earlier.label, result.later.label) == ("2026-03", "2026-06")
    assert (result.earlier.start, result.earlier.end) == (date(2026, 3, 1), date(2026, 4, 1))
    assert "maret" not in result.question_without_periods.casefold() and "juni" not in result.question_without_periods.casefold()
    assert "sumatera utara" in result.question_without_periods


def test_ranges_are_labelled_as_ranges() -> None:
    ranges = PeriodUnderstanding(compare=True, periods=[PeriodSpec(start="2026-03", end="2026-05"), PeriodSpec(start="2026-06", end="2026-08")])
    result = to_comparison(ranges, "compare", TODAY)
    assert result is not None and (result.earlier.label, result.later.label) == ("2026-03 to 2026-05", "2026-06 to 2026-08")


def test_a_wrong_or_unsafe_answer_is_dropped() -> None:
    assert to_comparison(PeriodUnderstanding(compare=False), "q", TODAY) is None
    assert to_comparison(PeriodUnderstanding(compare=True, periods=[PeriodSpec(start="2026-03", end="2026-03")]), "q", TODAY) is None
    assert to_comparison(_two("2026-03", "2026-03"), "q", TODAY) is None
    assert to_comparison(_two("2026-13", "2026-03"), "q", TODAY) is None
    assert to_comparison(_two("March", "2026-03"), "q", TODAY) is None
    assert to_comparison(_two("2090-03", "2026-03"), "q", TODAY) is None
    backwards = PeriodUnderstanding(compare=True, periods=[PeriodSpec(start="2026-06", end="2026-03"), PeriodSpec(start="2026-01", end="2026-01")])
    assert to_comparison(backwards, "q", TODAY) is None


def test_a_failing_model_means_the_normal_question() -> None:
    provider = Provider(RuntimeError("boom"))
    assert asyncio.run(understand_periods(provider, QUESTION, TODAY)) is None and provider.calls == 1

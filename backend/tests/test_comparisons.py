from __future__ import annotations

import asyncio
from datetime import date

from app.ask_data import comparisons as cmp
from app.ask_data import value_filters as vf
from tests.test_drill_across import SOURCES, _Executor, _two_dataset_ctx


def test_two_periods_are_found_with_or_without_a_year_on_each() -> None:
    found = cmp.detect_period_comparison("Compare the approval rate by region from March to May with June to August 2026")
    assert (found.earlier.start, found.earlier.end) == (date(2026, 3, 1), date(2026, 6, 1))
    assert (found.later.start, found.later.end) == (date(2026, 6, 1), date(2026, 9, 1))
    assert "March" not in found.question_without_periods and "region" in found.question_without_periods
    quarters = cmp.detect_period_comparison("approval rate Q2 2026 versus Q1 2026 by channel")
    assert (quarters.earlier.label, quarters.later.label) == ("Q1 2026", "Q2 2026")  # ordered by date, not by the question
    assert cmp.detect_period_comparison("Compare Q1 vs Q2 2026 by channel").later.label == "Q2 2026"
    months = cmp.detect_period_comparison("compare approval rate March 2026 with April 2026")
    assert months.earlier.label == "2026-03" and months.later.label == "2026-04"


def test_a_plain_period_or_a_lone_comparison_word_is_not_a_comparison() -> None:
    assert cmp.detect_period_comparison("approval rate by region from June to August 2026") is None
    assert cmp.detect_period_comparison("compare approval rate by region and channel") is None
    assert cmp.detect_period_comparison("compare March 2026 with March 2026") is None
    assert cmp.detect_period_comparison("compare Q1 2026, Q2 2026 and Q3 2026") is None


def test_the_overall_benchmark_and_its_margin_are_read_from_the_question() -> None:
    above = cmp.detect_benchmark("Which regions are above the overall approval rate?")
    assert (above.direction, above.margin) == ("above", 0.0) and above.breakdown_text.endswith("by regions")
    below = cmp.detect_benchmark("Which regions are more than 15 points below the overall approval rate?")
    assert (below.direction, below.margin) == ("below", 15.0)
    indonesian = cmp.detect_benchmark("Wilayah mana yang di bawah rata-rata keseluruhan?")
    assert indonesian.direction == "below"
    assert cmp.detect_benchmark("What is the approval rate by region?") is None


def test_periods_merge_into_later_earlier_and_change() -> None:
    earlier = {"columns": ["region", "metric_value"], "rows": [{"region": "Bali", "metric_value": 6.0}, {"region": "Aceh", "metric_value": 0.0}], "execution_ms": 3}
    later = {"columns": ["region", "metric_value"], "rows": [{"region": "Bali", "metric_value": 15.6}, {"region": "Aceh", "metric_value": 2.0}, {"region": "Riau", "metric_value": 4.0}], "execution_ms": 4}
    merged = cmp.merge_periods([earlier, later])
    assert merged["columns"] == ["region", "metric_value", "previous_value", "change", "change_pct"]
    by_region = {r["region"]: r for r in merged["rows"]}
    assert by_region["Bali"]["change"] == 9.6 and by_region["Bali"]["change_pct"] == 160.0
    assert by_region["Aceh"]["change"] == 2.0 and by_region["Aceh"]["change_pct"] is None  # no percentage from zero
    assert by_region["Riau"]["previous_value"] is None and by_region["Riau"]["change"] is None
    assert merged["execution_ms"] == 7


def test_the_benchmark_keeps_only_groups_beyond_the_margin() -> None:
    grouped = {"columns": ["region", "metric_value"], "rows": [{"region": "A", "metric_value": 20.0}, {"region": "B", "metric_value": 11.0}, {"region": "C", "metric_value": 5.0}]}
    overall = {"columns": ["metric_value"], "rows": [{"metric_value": 10.0}]}
    above = cmp.merge_benchmark([grouped, overall], "above", 0.0)
    assert [r["region"] for r in above["rows"]] == ["A", "B"] and above["rows"][0]["difference"] == 10.0
    assert above["columns"] == ["region", "metric_value", "overall_value", "difference"]
    assert [r["region"] for r in cmp.merge_benchmark([grouped, overall], "above", 5.0)["rows"]] == ["A"]
    assert [r["region"] for r in cmp.merge_benchmark([grouped, overall], "below", 4.0)["rows"]] == ["C"]
    assert cmp.merge_benchmark([grouped, overall], "below", 6.0)["rows"] == []  # nothing is that far below


def _plan(question: str):
    vf.clear_cache()
    return asyncio.run(
        cmp.plan_comparison(
            question=question,
            primary_metric="approval_rate",
            semantic_context=_two_dataset_ctx(),
            qualified_sources=SOURCES,
            executor=_Executor(),
            state={},
        )
    )


def test_a_period_comparison_runs_the_metric_once_per_period() -> None:
    drill, notes = _plan("Compare the approval rate by region from March to May with June to August 2026")
    assert drill["kind"] == "periods" and drill["meta"] == {"previous": "2026-03 to 2026-05", "current": "2026-06 to 2026-08"}
    first, second = drill["queries"]
    assert "DATE '2026-03-01'" in first["sql"] and "DATE '2026-06-01'" in first["sql"] and "DATE '2026-09-01'" not in first["sql"]
    assert "DATE '2026-06-01'" in second["sql"] and "DATE '2026-09-01'" in second["sql"]
    assert all("GROUP BY d.region_name" in q["sql"] for q in drill["queries"])
    assert all('FROM "hive"."default"."credit_applications"' in q["sql"] for q in drill["queries"])


def test_a_period_comparison_keeps_the_value_filter_in_both_queries() -> None:
    drill, notes = _plan("Compare the approval rate for Jawa Barat from March to May with June to August 2026 by channel")
    assert all("d.region_name = 'Jawa Barat'" in q["sql"] for q in drill["queries"])
    assert any("Jawa Barat" in n for n in notes)


def test_a_benchmark_question_runs_the_grouped_query_and_the_overall_one() -> None:
    drill, _ = _plan("Which regions are more than 15 points below the overall approval rate?")
    assert drill["kind"] == "benchmark" and drill["meta"] == {"direction": "below", "margin": 15.0}
    grouped, overall = drill["queries"]
    assert "GROUP BY d.region_name" in grouped["sql"]
    assert "GROUP BY" not in overall["sql"] and overall["resolution"]["dimensions"] == []


def test_ordinary_questions_and_unplaceable_benchmarks_are_left_alone() -> None:
    assert _plan("What is the approval rate by region?") is None
    assert _plan("Is the approval rate above the overall rate?") is None  # nothing to group by
    assert _plan("Compare the approval rate by region") is None


def test_merge_dispatch_uses_the_kind() -> None:
    result = {"columns": ["metric_value"], "rows": [{"metric_value": 1}]}
    merged = cmp.merge_drill_results({"kind": "periods", "queries": [{}, {}]}, [result, result])
    assert merged["columns"][-3:] == ["previous_value", "change", "change_pct"]

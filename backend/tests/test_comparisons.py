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


def _plan(question: str, periods_hint=None):
    vf.clear_cache()
    return asyncio.run(
        cmp.plan_comparison(
            question=question,
            primary_metric="approval_rate",
            semantic_context=_two_dataset_ctx(),
            qualified_sources=SOURCES,
            executor=_Executor(),
            state={},
            periods_hint=periods_hint,
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


def test_a_range_without_a_year_means_its_most_recent_finished_occurrence() -> None:
    today = date(2026, 11, 3)
    found = cmp.detect_period_comparison("Compare late rate between March-May and June-August", today)
    assert (found.earlier.start, found.earlier.end) == (date(2026, 3, 1), date(2026, 6, 1))
    assert (found.later.start, found.later.end) == (date(2026, 6, 1), date(2026, 9, 1))
    early = cmp.detect_period_comparison("Compare late rate between March-May and June-August", date(2026, 7, 1))
    assert early.earlier.start == date(2025, 3, 1) and early.later.start == date(2025, 6, 1)  # June-August is not over yet
    assert cmp.detect_period_comparison("Compare Q1 vs Q2", today).later.label == "Q2 2026"


def test_compare_with_the_overall_value_is_read_as_a_benchmark_without_filtering() -> None:
    for text in (
        "How does Kalimantan Timur late delivery rate compare to the overall rate?",
        "Kalimantan Timur versus overall late delivery rate",
        "Bandingkan tingkat keterlambatan Jawa Timur dengan rata-rata keseluruhan",
    ):
        found = cmp.detect_benchmark(text)
        assert found is not None and found.direction == "any", text
    assert cmp.detect_benchmark("compare approval rate by region and channel") is None
    assert cmp.detect_benchmark("compare average delivery days by carrier") is None


def test_one_named_group_is_compared_with_the_overall_value_of_the_whole_data_set() -> None:
    drill, notes = _plan("How does the approval rate of Jawa Barat compare to the overall rate?")
    assert drill["kind"] == "benchmark" and drill["meta"]["direction"] == "any"
    grouped, overall = drill["queries"]
    assert "d.region_name = 'Jawa Barat'" in grouped["sql"] and "GROUP BY" not in grouped["sql"]
    assert "Jawa Barat" not in overall["sql"] and "GROUP BY" not in overall["sql"]
    assert any("Jawa Barat" in n for n in notes)
    merged = cmp.merge_drill_results(drill, [{"columns": ["metric_value"], "rows": [{"metric_value": 23.15}]}, {"columns": ["metric_value"], "rows": [{"metric_value": 11.3}]}])
    assert merged["columns"] == ["metric_value", "overall_value", "difference"]
    assert merged["rows"] == [{"metric_value": 23.15, "overall_value": 11.3, "difference": 11.85}]


def test_every_group_is_listed_when_compared_with_the_overall_value() -> None:
    drill, _ = _plan("Compare the approval rate by region with the overall rate")
    assert "GROUP BY d.region_name" in drill["queries"][0]["sql"]
    grouped = {"columns": ["region_name", "metric_value"], "rows": [{"region_name": "A", "metric_value": 5}, {"region_name": "B", "metric_value": 20}]}
    merged = cmp.merge_drill_results(drill, [grouped, {"columns": ["metric_value"], "rows": [{"metric_value": 10}]}])
    assert [(r["region_name"], r["difference"]) for r in merged["rows"]] == [("B", 10.0), ("A", -5.0)]
    assert _plan("Compare the approval rate with the overall rate") is None  # no group to compare


def test_periods_read_by_the_model_run_like_a_regex_comparison() -> None:
    from app.ask_data.period_understanding import PeriodSpec, PeriodUnderstanding, to_comparison
    from datetime import date

    question = "Bisa bantu compare approval rate di Jawa Barat maret versus juni 2026 per channel"
    assert _plan(question) is None  # the regex cannot read this wording, so nothing is compared without the model
    hint = to_comparison(
        PeriodUnderstanding(compare=True, periods=[PeriodSpec(start="2026-03", end="2026-03"), PeriodSpec(start="2026-06", end="2026-06")]),
        question,
        date(2026, 11, 4),
    )
    drill, notes = _plan(question, hint)
    assert drill["kind"] == "periods" and drill["meta"] == {"previous": "2026-03", "current": "2026-06"}
    first, second = drill["queries"]
    assert "DATE '2026-03-01'" in first["sql"] and "DATE '2026-04-01'" in first["sql"]
    assert "DATE '2026-06-01'" in second["sql"] and "DATE '2026-07-01'" in second["sql"]
    assert all("GROUP BY d.application_channel" in q["sql"] for q in drill["queries"])


def test_the_commonest_pair_phrasings_are_read_without_the_model() -> None:
    from datetime import date

    today = date(2026, 11, 4)
    for question in (
        "Bisa bantu compare data late delivery di sumatera utara antara maret dan juni",
        "Bandingkan late delivery Sumatera Utara bulan Maret dengan bulan Juni",
        "Compare late delivery in Sumatera Utara between March and June",
    ):
        found = cmp.detect_period_comparison(question, today)
        assert found is not None, question
        assert (found.earlier.label, found.later.label) == ("2026-03", "2026-06"), question
        assert not any(word in found.question_without_periods.casefold() for word in ("maret", "juni", "march", "june")), question
    dated = cmp.detect_period_comparison("compare orders between March 2025 and June 2026", today)
    assert (dated.earlier.label, dated.later.label) == ("2025-03", "2026-06")


def test_a_range_or_a_total_between_two_months_is_not_a_comparison() -> None:
    from datetime import date

    today = date(2026, 11, 4)
    assert cmp.detect_period_comparison("Total orders between March and June", today) is None  # no comparison word: one range
    assert cmp.detect_period_comparison("Compare carriers from March to June", today) is None  # one range, not two periods

"""An overview starts with the metrics the model author marked as headline, whatever the planner proposed."""
from __future__ import annotations

import asyncio

from app.ask_data.agent_mode import AgentStep, _humanize_catalog, fallback_steps, plan_steps
from tests.test_agent_mode import Provider

CATALOG = [
    {"name": "harga_rata", "description": "Total value divided by liters.", "allowed_dimensions": ["tanggal_transaksi", "regional", "produk"], "headline": 0},
    {"name": "tingkat_keterlambatan", "description": "Percentage of late deliveries (tingkat).", "allowed_dimensions": ["tanggal_transaksi", "regional", "produk"], "headline": 1},
    {"name": "total_nilai", "description": "Total value, in rupiah.", "allowed_dimensions": ["tanggal_transaksi", "regional", "produk"], "headline": 0},
    {"name": "total_volume", "description": "Total fuel delivered, in KL. Total of all deliveries.", "allowed_dimensions": ["tanggal_transaksi", "regional", "produk"], "headline": 2},
]
QUESTION = "Gimana kondisi penyaluran BBM kita secara keseluruhan?"


def test_an_overview_without_a_headline_metric_is_replaced_by_the_plan_built_from_them() -> None:
    proposed = [
        AgentStep(kind="data", question="Total Nilai", metric="total_nilai"),
        AgentStep(kind="data", question="Harga Rata", metric="harga_rata"),
        AgentStep(kind="data", question="Total Nilai per bulan", metric="total_nilai"),
    ]
    steps = asyncio.run(plan_steps(Provider(proposed), question=QUESTION, catalog=CATALOG, has_knowledge=False))
    metrics = [s.metric for s in steps]
    assert metrics[0] == "tingkat_keterlambatan" and "total_volume" in metrics
    assert any("per bulan" in s.question for s in steps) and any("per regional" in s.question for s in steps)
    assert "harga_rata" not in metrics


def test_a_plan_that_already_has_a_headline_metric_is_kept() -> None:
    proposed = [AgentStep(kind="data", question="Tingkat Keterlambatan", metric="tingkat_keterlambatan"), AgentStep(kind="data", question="Total Nilai", metric="total_nilai")]
    steps = asyncio.run(plan_steps(Provider(proposed), question=QUESTION, catalog=CATALOG, has_knowledge=False))
    # What the planner chose is kept, and the group that stands out is added because the plan had none.
    assert [s.metric for s in steps] == ["tingkat_keterlambatan", "total_nilai", "tingkat_keterlambatan"]
    assert steps[-1].question.endswith("per regional")


def test_a_question_that_is_not_an_overview_is_left_to_the_planner() -> None:
    proposed = [AgentStep(kind="data", question="Total Nilai", metric="total_nilai"), AgentStep(kind="data", question="Harga Rata", metric="harga_rata")]
    steps = asyncio.run(plan_steps(Provider(proposed), question="Kenapa nilai penyaluran turun?", catalog=CATALOG, has_knowledge=False))
    assert [s.metric for s in steps] == ["total_nilai", "harga_rata"]


def test_the_fallback_prefers_the_headline_rate_and_volume() -> None:
    steps = fallback_steps(QUESTION, CATALOG, [], "id", prefer_headline=True)
    assert steps[0].metric == "tingkat_keterlambatan"
    assert steps[1].metric == "total_volume"


def test_the_catalog_given_to_the_planner_marks_the_headline_metrics() -> None:
    marked = {m["metric"]: m.get("headline") for m in _humanize_catalog(CATALOG)}
    assert marked["tingkat_keterlambatan"] == 1 and marked["total_volume"] == 2 and marked["total_nilai"] is None


def test_an_overview_gets_a_step_by_a_group_when_the_plan_has_none() -> None:
    proposed = [
        AgentStep(kind="data", question="Total Volume", metric="total_volume"),
        AgentStep(kind="data", question="Ketepatan Pengiriman", metric="harga_rata"),
        AgentStep(kind="data", question="Tingkat Keterlambatan", metric="tingkat_keterlambatan"),
        AgentStep(kind="data", question="Total Volume per bulan", metric="total_volume"),
    ]
    steps = asyncio.run(plan_steps(Provider(proposed), question=QUESTION, catalog=CATALOG, has_knowledge=False))
    assert len(steps) == 4
    assert [s.metric for s in steps][-1] == "tingkat_keterlambatan" and steps[-1].question.endswith("per regional")
    assert "harga_rata" not in [s.metric for s in steps]  # the step that was not a headline metric made room


def test_a_plan_that_already_breaks_down_by_a_group_is_left_alone() -> None:
    proposed = [
        AgentStep(kind="data", question="Tingkat Keterlambatan", metric="tingkat_keterlambatan"),
        AgentStep(kind="data", question="Tingkat Keterlambatan per regional", metric="tingkat_keterlambatan"),
    ]
    steps = asyncio.run(plan_steps(Provider(proposed), question=QUESTION, catalog=CATALOG, has_knowledge=False))
    assert [s.question for s in steps] == ["Tingkat Keterlambatan", "Tingkat Keterlambatan per regional"]

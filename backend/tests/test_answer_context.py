"""Context next to a number, the way Genie answers: the overall value next to a breakdown, the range the data covers,
and an investigation for a "why" follow-up that keeps the conversation going afterwards."""
from __future__ import annotations

from datetime import date

import pytest

duckdb = pytest.importorskip("duckdb")
pytest.importorskip("pytest_asyncio")

from app.ask_data.agent_mode import is_open_question  # noqa: E402
from app.ask_data.answer_context import coverage_label, no_data_message, period_outside_coverage  # noqa: E402
from replay_support import DATA, Replay, ScriptedModel  # noqa: E402

needs_data = pytest.mark.skipif(not (DATA / "orders.csv").exists(), reason="sample data not generated")
COVERAGE = {"first": "2026-01-01", "last": "2026-08-31"}


def test_questions_for_the_agent_in_everyday_indonesian_and_english() -> None:
    for text in (
        "Kenapa Kalimantan Timur bisa setinggi itu?",
        "Kalau saya mau perbaiki satu hal dulu, sebaiknya mulai dari mana?",
        "Gimana performa pengiriman kita secara keseluruhan?",
        "Buatkan ringkasan untuk atasan saya",
        "Berapa pesanan yang dibatalkan dan apakah ada hubungannya dengan keterlambatan?",
        "Kok bisa naik terus?",
        "What should we fix first?",
        "Give me a summary of delivery performance",
    ):
        assert is_open_question(text), text
    for text in (
        "Wilayah mana yang paling sering telat?",
        "Total order bulan Maret 2026",
        "Late rate per carrier di Jawa Timur",
        "Bandingkan Sumatera Utara Maret dengan Juni",
    ):
        assert not is_open_question(text), text


def test_a_period_outside_the_data_is_named_and_the_range_is_given() -> None:
    assert period_outside_coverage("Total orders in December 2025", COVERAGE) == "2025-12"
    assert period_outside_coverage("Total orders in March 2026", COVERAGE) is None
    assert period_outside_coverage("Total orders", COVERAGE) is None
    assert coverage_label(COVERAGE, "id") == "1 Januari 2026 sampai 31 Agustus 2026"
    message = no_data_message("Total order Desember 2025", COVERAGE, "id")
    assert message and "di luar data" in message and "Agustus 2026" in message
    assert period_outside_coverage("Orders from October to November 2026", COVERAGE, today=date(2026, 12, 1))


@needs_data
@pytest.mark.asyncio
async def test_a_breakdown_comes_with_the_overall_value_and_the_data_range(monkeypatch) -> None:
    replay = Replay(monkeypatch)
    r = await replay.ask("Late delivery rate per region")
    assert r.status == "SUCCESS" and r.data.rows[0]["delivery_shipments_region_name"] == "Kalimantan Timur"
    assert r.data.overall_value == pytest.approx(11.26, abs=0.01)  # the same metric without the breakdown
    assert r.data.data_coverage and r.data.data_coverage["first"].startswith("2026-01")
    assert len(replay.executor.context_queries) == 2 and "GROUP BY" not in replay.executor.context_queries[-1]
    # A single figure needs no overall value.
    r = await replay.ask("Total orders in March 2026")
    assert r.data.overall_value is None


@needs_data
@pytest.mark.asyncio
async def test_a_period_before_the_data_starts_is_said_so_instead_of_reported_as_zero(monkeypatch) -> None:
    replay = Replay(monkeypatch)
    r = await replay.ask("Total orders in December 2025")
    # COUNT gives one row of 0 there; the answer says the period is outside the data instead of reporting 0 orders.
    assert r.status == "NO_DATA" and r.data.row_count == 0
    assert "outside the data" in r.answer.direct_answer and "August 2026" in r.answer.direct_answer


@needs_data
@pytest.mark.asyncio
async def test_a_why_follow_up_is_investigated_and_the_next_follow_up_keeps_the_metric(monkeypatch) -> None:
    why = "kenapa bisa setinggi itu?"
    in_full = "Kenapa Late Delivery Rate di Kalimantan Timur tinggi?"
    model = ScriptedModel(
        rewrites={why: in_full, "kalau per bulan?": "Late delivery rate per bulan di Kalimantan Timur"},
        analysis={why},
        plans={  # without a metric pin: pinning needs the platform database, which the replay does not have
            in_full: [
                {"kind": "data", "question": "Late delivery rate per region", "why": "Posisi Kalimantan Timur"},
                {"kind": "data", "question": "Late delivery rate per carrier di Kalimantan Timur", "why": "Kurir mana"},
            ]
        },
    )
    replay = Replay(monkeypatch, model=model)
    await replay.ask("Wilayah mana yang late delivery rate-nya paling tinggi?", agent=True)
    r = await replay.ask(why, agent=True)
    assert r.strategy == "agent" and r.answer.direct_answer == "report"
    assert model.plan_payloads[-1]["question"] == in_full and model.plan_payloads[-1]["conversation"]
    report = model.report_payloads[-1]
    assert report["question_in_full"] == in_full and report["language"] == "id"
    assert report["steps"][0]["overall_value"] == pytest.approx(11.26, abs=0.01)
    assert "Something nobody can answer" not in r.answer.follow_up_questions
    assert model.calls.count("TurnReading") == 1  # the first turn needs none; the agent read the "why" once, its steps none
    # The agent's answer leaves its metric behind: the next follow-up continues the late rate.
    r = await replay.ask("kalau per bulan?", agent=True)
    assert r.status == "SUCCESS" and "is_late" in r.queries_run[-1] and "d.region_name = 'Kalimantan Timur'" in r.queries_run[-1]
    # The steps ran in their own sessions, which are gone afterwards.
    assert not [s for s in replay.service.history.turns if s.startswith("agent-")]


@needs_data
@pytest.mark.asyncio
async def test_a_question_the_agent_leaves_is_read_only_once(monkeypatch) -> None:
    model = ScriptedModel(rewrites={"kalau per carrier?": "Late delivery rate per carrier di Jawa Timur"})
    replay = Replay(monkeypatch, model=model)
    await replay.ask("Late delivery rate di Jawa Timur", agent=True)
    r = await replay.ask("kalau per carrier?", agent=True)
    assert r.strategy == "governed" and "GROUP BY d.carrier" in r.queries_run[-1]
    assert model.calls.count("TurnReading") == 1 and "AgentPlan" not in model.calls


@needs_data
@pytest.mark.asyncio
async def test_which_region_in_indonesian_is_a_ranking_with_the_overall_value(monkeypatch) -> None:
    question = "Wilayah mana yang pengirimannya paling sering telat, dan seberapa jauh bedanya dengan yang lain?"
    replay = Replay(monkeypatch, model=ScriptedModel(choices={question: "late_delivery_rate"}))
    r = await replay.ask(question)
    assert r.data.row_count == 8 and r.data.rows[0]["delivery_shipments_region_name"] == "Kalimantan Timur"
    assert r.data.overall_value == pytest.approx(11.26, abs=0.01)
    r = await replay.ask("Kurir mana yang late delivery rate-nya paling tinggi?")
    assert r.data.rows[0]["delivery_shipments_carrier"] == "NusaCargo"
    r = await replay.ask("Late delivery rate tiap kurir")
    assert r.data.row_count == 3


def test_the_data_range_is_only_told_when_the_question_is_about_time() -> None:
    from app.ask_data.answer_context import asks_about_time

    assert asks_about_time("Ringkasan temuan utama minggu ini")
    assert asks_about_time("Total order Desember 2025")
    assert not asks_about_time("Bagaimana performa pengiriman kita secara keseluruhan?")
    assert not asks_about_time("Wilayah mana yang paling sering telat?")

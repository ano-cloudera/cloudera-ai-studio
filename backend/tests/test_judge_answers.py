"""The answer judge (scripts/judge_answers.py) and the POV conversation it judges, replayed offline on the sample data.

Offline the language model is scripted, so only what the pipeline decides is judged here: the route, the metric, the top
row, the rows, the overall value and the agent steps. The words and numbers of the text are judged on a live Backend
with the real model (see the script's usage).
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("judge_answers", REPO / "scripts" / "judge_answers.py")
ja = importlib.util.module_from_spec(_spec)
sys.modules["judge_answers"] = ja
_spec.loader.exec_module(ja)

CASES = json.loads((REPO / "samples" / "fulfillment" / "judge_conversation.json").read_text(encoding="utf-8"))
DECISIONS = ("status", "route", "metric", "first_row", "min_rows", "overall_value", "min_steps")


def _response(text: str, **extra) -> dict:
    return {"status": "SUCCESS", "strategy": "governed", "answer": {"direct_answer": text}, "data": {"rows": [], "governed_metric": "late_delivery_rate"}, **extra}


def test_numbers_are_read_with_a_decimal_comma_or_point_and_rounding() -> None:
    assert ja.states_number("Kalimantan Timur 23,15% dari 11.26%", 23.15)
    assert ja.states_number("sekitar 23.2%", 23.15) and ja.states_number("23,1 persen", 23.15)
    assert not ja.states_number("sekitar 23%", 23.15) and not ja.states_number("2.315", 23.15)
    assert ja.numbers_in("1.074 pesanan, 3,78%") == [1074.0, 3.78]


def test_a_wrong_route_a_missing_number_english_text_and_an_echoed_label_all_fail() -> None:
    expect = {"route": "agent", "numbers": [11.26], "mentions": [["keterlambatan", "telat"]]}
    english = _response("Overall, the average delivery time is 2.58 days and the late rate is shown by region.")
    failed = {name for name, ok, _ in ja.judge(expect, english) if not ok}
    assert {"route", "states 11.26", "mentions keterlambatan | telat", "language id"} <= failed
    good = _response("Tingkat keterlambatan kita 11,26% secara keseluruhan.", strategy="agent", calculation={"steps": ["1", "2", "3"]})
    assert all(ok for _, ok, _ in ja.judge({**expect, "min_steps": 3}, good))
    echo = _response("Metrik yang tersedia:\n- Late Rate By Order Attributes: Late Rate by Order Attributes (%)")
    assert "no repeated labels" in {name for name, ok, _ in ja.judge({}, echo) if not ok}


def test_the_conversation_report_counts_passes_and_keeps_going_after_an_error() -> None:
    answers = iter([_response("Kalimantan Timur 23,15%"), RuntimeError("timeout")])

    def ask(question, session):
        item = next(answers)
        if isinstance(item, Exception):
            raise item
        return item

    cases = {"name": "t", "turns": [{"question": "a", "expect": {"numbers": [23.15]}}, {"question": "b", "expect": {}}]}
    result = ja.run_conversation(ask, cases)
    assert (result["passed"], result["total"]) == (1, 2)
    assert result["turns"][1]["failed"][0]["check"] == "request"


duckdb = pytest.importorskip("duckdb")


@pytest.mark.skipif(not (REPO / "samples" / "fulfillment" / "data" / "orders.csv").exists(), reason="sample data not generated")
@pytest.mark.asyncio
async def test_the_pov_conversation_takes_the_right_route_metric_and_rows(monkeypatch) -> None:
    from app.ask_data import agent_mode
    from replay_support import Replay, ScriptedModel

    # Offline there is no platform database to resolve a pinned metric; the step's own words name it instead.
    monkeypatch.setattr(agent_mode, "_metric_names", lambda catalog: set())
    turns = [t["question"] for t in CASES["turns"]]
    model = ScriptedModel(
        rewrites={
            turns[4]: "Late delivery rate per kurir di Kalimantan Timur",
            turns[5]: "Late delivery rate per bulan",
            turns[6]: "Bandingkan late delivery rate Sumatera Utara Januari sampai April 2026 dengan Juni sampai Agustus 2026",
        },
        plans={
            turns[3]: [
                {"kind": "data", "question": "Late delivery rate per kurir di Kalimantan Timur", "why": "w"},
                {"kind": "data", "question": "Late delivery rate per bulan di Kalimantan Timur", "why": "w"},
            ]
        },
    )
    replay = Replay(monkeypatch, model, agent_loop="plan")  # the script gives the planner's steps
    report = []
    for turn in CASES["turns"]:
        response = await replay.ask(turn["question"], agent=True)
        payload = response._response.model_dump(mode="json")
        expect = {k: v for k, v in (turn.get("expect") or {}).items() if k in DECISIONS}
        failed = [(name, seen) for name, ok, seen in ja.judge(expect, payload, language="none") if not ok and name not in ("answered", "no repeated labels")]
        report.append((turn["question"][:60], failed))
    assert [r for r in report if r[1]] == []


def test_numbers_are_read_whole_whatever_their_separators() -> None:
    numbers_in = ja.numbers_in
    assert numbers_in("Jumlah SPBU kita adalah 3000.") == [3000.0]
    assert numbers_in("4.996.168 KL dan 2.056 KL") == [4996168.0, 2056.0]
    assert 11716.55 in numbers_in("Rp 11.716,55") and 11716.55 in numbers_in("11,716.55")
    assert numbers_in("34,54% dan 23.15%") == [34.54, 23.15]
    assert ja.states_number("Jumlah SPBU kita adalah 3000.", 3000)


def test_the_judge_reads_the_answer_from_the_stream_the_ui_uses() -> None:
    lines = [
        b": keep-alive\n",
        b'data: {"type": "progress", "stage": "understanding", "label": "Reading"}\n',
        b"\n",
        b'data: {"type": "done", "response": {"status": "SUCCESS", "strategy": "governed", "answer": {"direct_answer": "16,07%"}}}\n',
    ]
    assert ja.done_response(lines)["answer"]["direct_answer"] == "16,07%"
    with pytest.raises(RuntimeError):
        ja.done_response([b": keep-alive\n"])


def test_recommendations_count_in_the_implications_or_as_a_list_in_the_report() -> None:
    def actions(answer: dict) -> bool:
        return dict((name, ok) for name, ok, _ in ja.judge({"needs_actions": True}, _response("", answer=answer)))["actions"]

    assert actions({"direct_answer": "x", "business_implications": ["Audit armada"]})
    assert actions({"direct_answer": "x", "executive_summary": "### Rekomendasi\n1. Audit armada di Sorong\n2. Tambah slot muat"})
    assert not actions({"direct_answer": "x", "executive_summary": "Papua Maluku 34,5%, tertinggi."})

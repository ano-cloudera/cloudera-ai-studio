from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.ask_data.benchmarks import extract_value, judge_example, run_examples, summarize_run
from app.core.models import AnalysisOutput, AskDataResponse, QueryData, Timings
from app.workspace.semantic_knowledge import (
    ExampleQuestion,
    SemanticKnowledge,
    read_semantic_knowledge,
    write_semantic_knowledge,
)


def _response(rows, status="SUCCESS") -> AskDataResponse:
    return AskDataResponse(
        request_id="r", session_id="s", status=status, provider="gemini", model="m", strategy="governed",
        answer=AnalysisOutput(direct_answer="ok", executive_summary="", insights=[], business_implications=[], caveats=[], data_reference=""),
        data=QueryData(columns=list(rows[0]) if rows else [], rows=rows, row_count=len(rows)), chart_spec=None, timings=Timings(),
        governed_sql="SELECT 1",
    )


def test_knowledge_is_stored_per_model_and_old_shapes_do_not_break_reading() -> None:
    stored = write_semantic_knowledge({"other": 1}, "m1", SemanticKnowledge(instructions="Late means after the service level.", examples=[ExampleQuestion(question="  How many   orders? ", expected_value=8000)]))
    assert stored["other"] == 1
    back = read_semantic_knowledge(stored, "m1")
    assert back.instructions.startswith("Late") and back.examples[0].question == "How many orders?"
    assert read_semantic_knowledge(stored, "m2") == SemanticKnowledge()
    assert read_semantic_knowledge({"semantic_knowledge": {"m1": {"bogus": 1}}}, "m1") == SemanticKnowledge()
    with pytest.raises(ValidationError):
        ExampleQuestion(question="x", tolerance=-1)


def test_the_value_comes_from_the_row_the_example_points_at() -> None:
    rows = [{"region": "Kalimantan Timur", "metric_value": 23.15}, {"region": "Jawa Timur", "metric_value": 16.34}]
    response = _response(rows)
    assert extract_value(response, None) == 23.15
    assert extract_value(response, "jawa timur") == 16.34
    assert extract_value(response, "Bali") is None
    assert extract_value(_response([{"metric_value": 16.34}]), "Jawa Timur") == 16.34  # filtered to one row by the question
    assert extract_value(_response([]), None) is None


def test_an_example_passes_inside_the_tolerance_and_fails_outside_it() -> None:
    response = _response([{"metric_value": 23.15}])
    ok = judge_example(ExampleQuestion(question="q", expected_value=23.1, tolerance=0.1), response)
    assert ok["status"] == "pass"
    bad = judge_example(ExampleQuestion(question="q", expected_value=20, tolerance=0.1), response)
    assert bad["status"] == "fail" and "Expected 20, got 23.15" in bad["message"]
    unchecked = judge_example(ExampleQuestion(question="q"), response)
    assert unchecked["status"] == "answered"
    assert judge_example(ExampleQuestion(question="q", expected_value=1), _response([{"metric_value": 1}], status="UNSUPPORTED"))["status"] == "error"
    assert judge_example(ExampleQuestion(question="q", expected_value=1), None, "boom")["message"] == "boom"


def test_a_run_keeps_going_after_an_error_and_scores_only_checked_examples() -> None:
    class Service:
        def normalize_request(self, request):
            return request

        async def run(self, request):
            if "fail" in request.question:
                raise RuntimeError("provider down")
            return _response([{"metric_value": 8000}])

    examples = [ExampleQuestion(question="orders", expected_value=8000, tolerance=0), ExampleQuestion(question="fail me", expected_value=1), ExampleQuestion(question="no number")]
    results = asyncio.run(run_examples(Service(), examples=examples, provider="gemini", model="m", semantic_model=("id", "Fulfillment")))
    assert [r["status"] for r in results] == ["pass", "error", "answered"]
    run = summarize_run(results, 1)
    assert (run.passed, run.total, run.published_version) == (1, 2, 1)

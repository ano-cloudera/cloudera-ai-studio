from __future__ import annotations

from pathlib import Path

from app.core.models import AnalysisOutput

PROMPT = Path(__file__).resolve().parents[1] / "prompts" / "result_analyst.md"


def _output(**extra) -> AnalysisOutput:
    return AnalysisOutput(direct_answer="x", executive_summary="", insights=[], business_implications=[], caveats=[], data_reference="r", **extra)


def test_follow_up_questions_are_cleaned_deduplicated_and_capped_at_three() -> None:
    out = _output(follow_up_questions=["  Break it down by region ", "Break it down by region", "Compare with — June", "", "a", "b"])
    assert out.follow_up_questions == ["Break it down by region", "Compare with, June", "a"]


def test_an_answer_without_follow_ups_or_with_garbage_is_still_valid() -> None:
    assert _output().follow_up_questions == []
    assert _output(follow_up_questions="not a list").follow_up_questions == []


def test_the_analyst_prompt_asks_for_conversation_not_a_report() -> None:
    text = PROMPT.read_text(encoding="utf-8")
    assert "follow_up_questions" in text and "Never write labels such as" in text
    assert "Operational hypotheses" not in text.split("## The fields")[1]  # the speculative block is gone

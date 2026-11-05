"""Reading a turn in the light of the conversation: when the rewrite is used, and when the question stays as written."""
from __future__ import annotations

import pytest

from app.ask_data.conversation import TurnReading, looks_like_small_talk, previous_turns, read_turn
from app.llm.base import ProviderError

pytest.importorskip("pytest_asyncio")

HISTORY = [
    {
        "question": "Late delivery rate in Jawa Timur",
        "answer": {"direct_answer": "The late rate in Jawa Timur is 16.34%."},
        "rows": [{"metric_value": 16.34}],
        "session_frame": {"metric": "late_delivery_rate", "dimensions": [], "standalone_question": "Late delivery rate in Jawa Timur"},
    }
]


class Model:
    def __init__(self, reading: TurnReading | Exception) -> None:
        self.reading = reading
        self.calls = 0

    async def generate_structured(self, messages, model, **_):  # noqa: ANN001
        self.calls += 1
        if isinstance(self.reading, Exception):
            raise self.reading
        return self.reading


async def read(question: str, reading: TurnReading | Exception, history=HISTORY) -> tuple[TurnReading, Model]:  # noqa: ANN001
    model = Model(reading)
    return await read_turn(provider=model, question=question, history=history), model


@pytest.mark.asyncio
async def test_a_follow_up_is_answered_as_the_model_wrote_it_out() -> None:
    reading, _ = await read("and per carrier?", TurnReading(uses_previous=True, standalone_question="Late delivery rate per carrier in Jawa Timur"))
    assert reading.uses_previous and reading.standalone_question == "Late delivery rate per carrier in Jawa Timur"


@pytest.mark.asyncio
async def test_a_question_the_model_calls_standalone_is_kept_word_for_word() -> None:
    # Even when the model "improves" it: a fresh question never inherits an older filter.
    reading, _ = await read("Late rate per region", TurnReading(uses_previous=False, standalone_question="Late rate per region in Jawa Timur"))
    assert reading.standalone_question == "Late rate per region" and not reading.uses_previous


@pytest.mark.asyncio
async def test_the_first_question_and_small_talk_need_no_model() -> None:
    reading, model = await read("Total orders in March 2026", TurnReading(uses_previous=True, standalone_question="x"), history=[])
    assert reading.standalone_question == "Total orders in March 2026" and model.calls == 0
    reading, model = await read("terima kasih!", TurnReading(uses_previous=True, standalone_question="x"))
    assert reading.kind == "chat" and model.calls == 0


@pytest.mark.asyncio
async def test_without_the_model_the_question_is_used_as_written() -> None:
    reading, _ = await read("and per carrier?", ProviderError("down"))
    assert reading.standalone_question == "and per carrier?" and reading.rationale == "rewrite_failed"
    reading, _ = await read("and per carrier?", TurnReading(uses_previous=True, standalone_question=""))
    assert reading.standalone_question == "and per carrier?"


@pytest.mark.asyncio
async def test_a_runaway_rewrite_is_not_used() -> None:
    reading, _ = await read("why?", TurnReading(uses_previous=True, standalone_question="late rate " * 200))
    assert reading.standalone_question == "why?"


def test_small_talk_is_greetings_thanks_and_questions_about_the_assistant() -> None:
    for text in ("Halo", "hi!", "terima kasih", "kamu bisa apa?", "What can you do?", "data apa saja yang bisa ditanyakan?"):
        assert looks_like_small_talk(text), text
    for text in ("Total orders in March", "halo, berapa total order bulan ini?", "Late rate per region"):
        assert not looks_like_small_talk(text), text


def test_the_previous_turns_show_how_each_was_read_and_its_first_rows() -> None:
    history = [
        {
            "question": "and per carrier?",
            "answer": {"direct_answer": "NusaCargo is the latest."},
            "rows": [{"carrier": f"C{i}", "metric_value": i} for i in range(9)],
            "session_frame": {"metric": "late_delivery_rate", "dimensions": ["carrier"], "standalone_question": "Late rate per carrier in Jawa Timur", "scope": "Jawa Timur"},
        }
    ]
    turn = previous_turns(history, labels={"late_delivery_rate": "Late delivery rate"})[0]
    assert turn == {
        "question": "and per carrier?",
        "read_as": "Late rate per carrier in Jawa Timur",
        "metric": "Late delivery rate",
        "breakdown": ["carrier"],
        "filters_and_period": "Jawa Timur",
        "answer": "NusaCargo is the latest.",
        "first_rows": [{"carrier": f"C{i}", "metric_value": i} for i in range(5)],
    }

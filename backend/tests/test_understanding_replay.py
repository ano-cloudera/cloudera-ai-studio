"""End to end on the sample data: with understanding 'llm' the model's reading, not the wording, decides the query.

Real: ChatService, the workflow, the compiler, the values read from the data. Stood in: the data source (DuckDB over the sample
CSVs) and the language model, which returns the reading a model would for each question.
"""
from __future__ import annotations

import asyncio

import pytest

from app.core.models import AskDataRequest
from tests.replay_support import Replay, ScriptedModel

REGION = "delivery_shipments_region_name"
CARRIER = "delivery_shipments_carrier"


class ReadingModel(ScriptedModel):
    def __init__(self, intents: dict[str, dict]) -> None:
        super().__init__()
        self.intents = intents
        self.intent_payloads: list[dict] = []

    async def generate_structured(self, messages, model, **kwargs):
        if model.__name__ == "QueryIntent":
            import json

            payload = json.loads(messages[1]["content"])
            self.intent_payloads.append(payload)
            self.calls.append("QueryIntent")
            return model.model_validate(self.intents[payload["question"]])
        return await super().generate_structured(messages, model, **kwargs)


def _ask(replay: Replay, question: str):
    before = len(replay.executor.queries)
    request = AskDataRequest(session_id=replay.session_id, question=question, provider="qwen", model="m", understanding="llm")
    response = asyncio.run(replay.service.run(request))
    return response, replay.executor.queries[before:]


@pytest.fixture()
def replay(monkeypatch):
    from app.ask_data import value_filters

    value_filters.clear_cache()
    model = ReadingModel({
        "Late delivery rate per carrier di Kalimantan Timur": {
            "metric": "late_delivery_rate", "breakdown": [CARRIER], "language": "id",
            "filters": [{"dimension": REGION, "values": ["kalimantan timur"]}],
        },
        "Tren keterlambatan Sumatera Utara per bulan": {
            "metric": "late_delivery_rate", "by_month": True, "language": "id",
            "filters": [{"dimension": REGION, "values": ["Sumatera Utara"]}],
        },
        "Late rate per kurir di Atlantis": {
            "metric": "late_delivery_rate", "breakdown": [CARRIER], "language": "id",
            "filters": [{"dimension": REGION, "values": ["Atlantis"]}],
        },
    })
    return Replay(monkeypatch, model)


def test_the_reading_decides_metric_breakdown_and_filter_and_the_values_come_from_the_data(replay) -> None:
    response, queries = _ask(replay, "Late delivery rate per carrier di Kalimantan Timur")
    assert response.status == "SUCCESS" and "QueryIntent" in replay.model.calls
    first = response.data.rows[0]
    assert "NusaCargo" in first.values() and abs(float(first["metric_value"]) - 32.2) < 0.06
    sql = queries[-1]
    assert "region_name = 'Kalimantan Timur'" in sql and "GROUP BY" in sql  # the model's lower case was matched to the data's value
    regions = next(d for d in replay.model.intent_payloads[0]["catalog"]["dimensions"]["delivery_shipments"] if d["key"] == REGION)
    assert "Kalimantan Timur" in regions["values"]  # the model was shown the real values
    assert any("Difilter ke" in c for c in response.answer.caveats)


def test_a_trend_by_month_is_ordered_by_month(replay) -> None:
    response, queries = _ask(replay, "Tren keterlambatan Sumatera Utara per bulan")
    assert response.status == "SUCCESS"
    assert "DATE_TRUNC('month'" in queries[-1] and "ORDER BY DATE_TRUNC" in queries[-1]
    months = [str(r[next(iter(r))]) for r in response.data.rows]
    assert months == sorted(months) and len(months) >= 6


def test_a_value_the_data_does_not_hold_is_left_out_and_said(replay) -> None:
    response, queries = _ask(replay, "Late rate per kurir di Atlantis")
    assert response.status == "SUCCESS"
    assert "Atlantis" not in queries[-1]
    assert any("Atlantis" in c for c in response.answer.caveats)


def test_the_rules_path_still_answers_when_understanding_is_not_asked_for(replay) -> None:
    request = AskDataRequest(session_id=replay.session_id, question="What is the late delivery rate by carrier?", provider="qwen", model="m")
    response = asyncio.run(replay.service.run(request))
    assert response.status == "SUCCESS" and "QueryIntent" not in replay.model.calls

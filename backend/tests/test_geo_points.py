"""A result by a dimension that carries coordinates in the semantic model says where each value is, so it can be mapped."""
from __future__ import annotations

import asyncio

from app.core.models import AskDataRequest
from tests.replay_support import Replay, WorstCaseModel

CARRIER = "delivery_shipments_carrier"


def test_the_coordinates_of_the_dimension_come_with_the_result(monkeypatch) -> None:
    from app.ask_data import answer_context, value_filters

    value_filters.clear_cache()
    replay = Replay(monkeypatch, WorstCaseModel())
    field = replay.context.registry.dataset_fields["delivery_shipments"][CARRIER]
    monkeypatch.setitem(field, "ai_context", {**(field.get("ai_context") or {}), "geo": {"NusaCargo": [-1.27, 116.83]}})
    request = AskDataRequest(session_id=replay.session_id, question="What is the late delivery rate by carrier?", provider="qwen", model="m")
    response = asyncio.run(replay.service.run(request))
    answer_context._COVERAGE.clear()
    value_filters.clear_cache()
    assert response.status == "SUCCESS" and CARRIER in response.data.columns
    assert response.data.geo_points == {CARRIER: {"NusaCargo": [-1.27, 116.83]}}


def test_a_result_without_such_a_dimension_has_none(monkeypatch) -> None:
    replay = Replay(monkeypatch, WorstCaseModel())
    assert replay.service._geo_points(["metric_value", CARRIER]) == {}

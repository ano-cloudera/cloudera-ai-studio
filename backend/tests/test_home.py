"""Home on the sample data: KPIs, trend, breakdown and map from governed queries only, kept for a while, and a briefing whose
figures are checked against them."""
from __future__ import annotations

import asyncio
import json

import pytest

from app.core.models import AskDataRequest
from app.home import dashboard
from tests.replay_support import Replay, WorstCaseModel

REQUEST = AskDataRequest(session_id="home", question="home", provider="qwen", model="m")


class BriefingModel(WorstCaseModel):
    """Writes one point with a figure from the input, and one with a figure that is in none of them."""

    def __init__(self) -> None:
        super().__init__()
        self.facts: dict = {}

    async def generate_structured(self, messages, model, **kwargs):
        if model.__name__ == "Briefing":
            self.calls.append("Briefing")
            self.facts = json.loads(messages[1]["content"])
            kpi = self.facts["kpis"][0]
            value = f"{kpi['value']:.1f}"
            return model.model_validate({
                "headline": f"{kpi['label']} {value} overall.",
                "points": [f"{kpi['label']} is {value} across all data.", "Something grew 987.6 percent."],
                "ask_next": ["Why is the late rate highest in Kalimantan Timur?"],
            })
        return await super().generate_structured(messages, model, **kwargs)


@pytest.fixture()
def replay(monkeypatch):
    from app.ask_data import answer_context, value_filters

    value_filters.clear_cache()
    dashboard.clear_cache()
    yield Replay(monkeypatch, BriefingModel())
    dashboard.clear_cache()
    answer_context._COVERAGE.clear()
    value_filters.clear_cache()


def test_home_is_built_from_governed_queries_and_kept(replay) -> None:
    home = asyncio.run(dashboard.build_home(replay.service, REQUEST))
    assert home["status"] == "ok" and home["kpis"]
    kpi = home["kpis"][0]
    assert isinstance(kpi["value"], float) and len(kpi["series"]) >= 6
    months = [p["month"] for p in kpi["series"]]
    assert months == sorted(months) and "change" in kpi and kpi["last_month"]["month"] == months[-1]
    assert home["breakdown"] and len(home["breakdown"]["rows"]) >= 3 and home["breakdown"]["overall_value"] is not None
    assert home["map"] is None  # no dimension of the sample carries coordinates
    assert not [c for c in replay.model.calls if c not in ("TurnReading",)]  # no language-model call
    ran = len(replay.executor.queries)
    again = asyncio.run(dashboard.build_home(replay.service, REQUEST))
    assert again == home and len(replay.executor.queries) == ran  # kept: nothing asked of the data source


def test_a_dimension_with_coordinates_is_put_on_the_home_map(replay, monkeypatch) -> None:
    _add_geo(replay, monkeypatch)
    home = asyncio.run(dashboard.build_home(replay.service, REQUEST))
    assert home["map"] and home["map"]["geo_points"]


def _add_geo(replay, monkeypatch) -> None:
    for dataset in ("fulfillment_orders", "delivery_shipments"):
        rows = replay.executor.con.execute(f"SELECT DISTINCT region_name FROM {dataset}").fetchall()
        field = replay.context.registry.dataset_fields[dataset][f"{dataset}_region_name"]
        geo = {str(name): [-1.0 - i, 110.0 + i] for i, (name,) in enumerate(rows)}
        monkeypatch.setitem(field, "ai_context", {**(field.get("ai_context") or {}), "geo": geo})


def test_the_briefing_keeps_only_points_whose_figures_are_in_the_home_figures(replay) -> None:
    briefing = asyncio.run(dashboard.build_briefing(replay.service, REQUEST))
    assert briefing["status"] == "ok" and briefing["headline"]
    assert len(briefing["points"]) == 1 and "987" not in briefing["points"][0]
    assert briefing["ask_next"]
    assert replay.model.facts["kpis"][0]["series"]  # the model was given the figures, not asked to find them

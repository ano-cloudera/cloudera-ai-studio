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
                "what_happened": f"{kpi['label']} is {value} across all data.",
                "why_it_matters": "Something grew 98765.4 percent.",
                "look_next": [f"{kpi['label']} at {value}.", "A made-up 412.7 figure."],
                "ask_next": ["Why is the late rate highest in Kalimantan Timur?"],
            })
        return await super().generate_structured(messages, model, **kwargs)


def _mark_home(replay, monkeypatch, marks: dict | None = None) -> None:
    """What the model's author declares in the metric editor: Show on Home (order), which way is good, a target."""
    marks = marks if marks is not None else {"late_delivery_rate": {"headline": 1, "better": "down", "target": 10}, "total_shipments": {"headline": 2, "better": "up"}}
    for name, config in marks.items():
        monkeypatch.setitem(replay.context.registry.metric_configs, name, {**replay.context.registry.metric_configs[name], **config})


@pytest.fixture()
def replay(monkeypatch):
    from app.ask_data import answer_context, value_filters

    value_filters.clear_cache()
    dashboard.clear_cache()
    replay = Replay(monkeypatch, BriefingModel())
    _mark_home(replay, monkeypatch)
    yield replay
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
    assert briefing["status"] == "ok" and briefing["headline"] and briefing["what_happened"]
    assert briefing["why_it_matters"] == ""  # its figure is in none of the Home figures, so it is left out
    assert len(briefing["look_next"]) == 1 and "412" not in briefing["look_next"][0]
    assert briefing["ask_next"]
    assert replay.model.facts["kpis"][0]["series"]  # the model was given the figures, not asked to find them


def test_home_is_served_from_disk_after_a_restart_and_refreshed_in_the_background_when_old(replay, monkeypatch, tmp_path) -> None:
    import diskcache

    dashboard._store = diskcache.Cache(str(tmp_path / "home"))  # the project storage

    async def scenario():
        first = await dashboard.build_home(replay.service, REQUEST)
        ran = len(replay.executor.queries)
        dashboard._memory.clear()  # a restart: the process memory is gone, the disk store is not
        again = await dashboard.build_home(replay.service, REQUEST)
        assert again == first and len(replay.executor.queries) == ran
        key = dashboard._key(replay.service, "home")
        kept = dashboard._read(replay.service, key)
        dashboard._write(replay.service, key, kept["payload"])
        monkeypatch.setattr(dashboard, "FRESH_SECONDS", -1)  # now everything kept counts as old
        served = await dashboard.build_home(replay.service, REQUEST)
        assert served == first  # served at once, not after the queries
        await asyncio.gather(*list(dashboard._tasks))
        assert len(replay.executor.queries) > ran  # and recomputed for the next viewer
        assert dashboard._read(replay.service, key)["payload"]["computed_at"]

    asyncio.run(scenario())


def test_warm_computes_home_before_the_first_viewer(replay) -> None:
    asyncio.run(dashboard.warm(replay.service))
    ran = len(replay.executor.queries)
    assert ran > 0
    home = asyncio.run(dashboard.build_home(replay.service, REQUEST))
    assert home["kpis"] and len(replay.executor.queries) == ran


def test_a_kpi_carries_the_unit_its_metric_declares() -> None:
    class Context:
        def metric_definition(self, name):
            return {"unit": "KL"} if name == "total_volume" else {}

    chat = type("Chat", (), {"dependencies": type("D", (), {"semantic_context": Context()})()})()
    assert dashboard._unit(chat, "total_volume") == "KL" and dashboard._unit(chat, "other") is None


def test_the_breakdown_shown_is_the_one_where_the_groups_differ_most(replay) -> None:
    home = asyncio.run(dashboard.build_home(replay.service, REQUEST))
    chosen = home["breakdown"]["dimension"]
    catalog = asyncio.run(replay.service.agent_catalog(REQUEST))
    main = dashboard._headline_metrics(catalog)[0]
    candidates = dashboard._compact_breakdowns(main, catalog)
    assert chosen in candidates and len(candidates) <= dashboard.MAX_CANDIDATES
    spreads = {}
    for key in candidates:
        response, _, _ = asyncio.run(replay.service.query_metric(REQUEST, dashboard.QueryIntent(metric=main["name"], breakdown=[key]), label="x"))
        spreads[key] = dashboard._spread(response)
    assert spreads[chosen] == max(spreads.values())


def test_the_language_of_home_is_asked_for_not_guessed_and_is_part_of_what_is_kept(replay) -> None:
    english = asyncio.run(dashboard.build_home(replay.service, REQUEST))
    indonesian = asyncio.run(dashboard.build_home(replay.service, REQUEST, language="id"))
    assert english["language"] == "en" and indonesian["language"] == "id"
    assert dashboard._key(replay.service, "home", "en") != dashboard._key(replay.service, "home", "id")


def test_home_shows_only_what_the_model_marks_and_says_so_when_nothing_is_marked(monkeypatch) -> None:
    from app.ask_data import value_filters

    value_filters.clear_cache()
    dashboard.clear_cache()
    replay = Replay(monkeypatch, BriefingModel())
    home = asyncio.run(dashboard.build_home(replay.service, REQUEST))
    assert home["status"] == "no_home_metrics" and home["kpis"] == [] and home["metric_count"] > 0
    assert not [q for q in replay.executor.queries if "metric_value" in q]  # no KPI is computed when nobody chose one


def test_the_kpis_carry_what_the_author_declared_and_the_standout_is_the_worse_group(replay) -> None:
    home = asyncio.run(dashboard.build_home(replay.service, REQUEST))
    assert [k["metric"] for k in home["kpis"]] == ["late_delivery_rate", "total_shipments"]  # in the declared order
    first = home["kpis"][0]
    assert first["better"] == "down" and first["target"] == 10 and first["previous_month"]
    standout = home["standout"]
    assert standout and standout["better"] == "down"
    differences = [g["difference"] for g in standout["groups"]]
    assert all(d > 0 for d in differences) and differences == sorted(differences, reverse=True)  # above the overall rate is worse

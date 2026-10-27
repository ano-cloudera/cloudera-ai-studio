from __future__ import annotations

from app.core.config import Settings
from app.services.ask_data_routing import resolve_ask_data_route


def _settings(**overrides) -> Settings:
    overrides.setdefault("local_agent_primary", False)
    return Settings(_env_file=None, **overrides)


def test_routing_mode_ossie() -> None:
    s = _settings(ask_data_routing="ossie", local_agent_primary=True)
    assert resolve_ask_data_route("Top 10 DC stok", s) == "ossie"


def test_routing_mode_v3() -> None:
    s = _settings(ask_data_routing="v3")
    assert resolve_ask_data_route("Berapa gross sales Q4?", s) == "v3"


def test_local_agent_primary_forces_v3_when_unresolved() -> None:
    s = _settings(ask_data_routing="auto", local_agent_primary=True)
    assert resolve_ask_data_route("Berapa gross sales?", s) == "v3"


def test_local_agent_primary_still_uses_ossie_when_metric_resolved() -> None:
    s = _settings(ask_data_routing="auto", local_agent_primary=True, local_agent_base_url="http://127.0.0.1:9766")
    resolution = {"status": "resolved", "metric": "sales_office_sell_in_value"}
    assert resolve_ask_data_route("Top 5 cabang penjualan terbesar", s, semantic_resolution=resolution) == "ossie"


def test_auto_resolved_metric_prefers_ossie() -> None:
    s = _settings(ask_data_routing="auto", local_agent_base_url="http://127.0.0.1:9766")
    resolution = {"status": "resolved", "metric": "gross_sales_amount"}
    assert resolve_ask_data_route("Berapa gross sales Oktober 2024?", s, semantic_resolution=resolution) == "ossie"


def test_auto_dc_ranking_prefers_ossie_when_metric_resolved() -> None:
    s = _settings(ask_data_routing="auto", local_agent_base_url="http://127.0.0.1:9766")
    resolution = {"status": "resolved", "metric": "sat_dc_stock_quantity"}
    assert (
        resolve_ask_data_route(
            "Top 10 DC dengan penumpukan stok tertinggi Q4 2024",
            s,
            semantic_resolution=resolution,
        )
        == "ossie"
    )


def test_auto_ambiguous_defaults_v3() -> None:
    s = _settings(ask_data_routing="auto")
    assert resolve_ask_data_route("Apa insight penjualan minggu ini?", s) == "v3"

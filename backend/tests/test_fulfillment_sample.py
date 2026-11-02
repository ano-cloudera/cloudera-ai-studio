from __future__ import annotations

import csv
import importlib.util
import json
import sys
from pathlib import Path

SAMPLE = Path(__file__).resolve().parents[2] / "samples" / "fulfillment"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(f"sample_{name}", SAMPLE / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    sys.path.insert(0, str(SAMPLE))
    spec.loader.exec_module(module)
    return module


def _rows(name: str) -> list[dict]:
    return list(csv.DictReader((SAMPLE / "data" / f"{name}.csv").open()))


def test_generation_is_reproducible(tmp_path, monkeypatch) -> None:
    generator = _load("generate_data")
    monkeypatch.setattr(generator, "OUT", tmp_path)
    generator.main()
    for name in ("orders", "shipments"):
        assert (tmp_path / f"{name}.csv").read_bytes() == (SAMPLE / "data" / f"{name}.csv").read_bytes()


def test_the_tables_share_keys_and_the_patterns_are_planted() -> None:
    orders, shipments = _rows("orders"), _rows("shipments")
    order_ids = {o["order_id"] for o in orders}
    assert all(s["order_id"] in order_ids for s in shipments)
    assert not {s["order_id"] for s in shipments} & {o["order_id"] for o in orders if o["order_status"] == "Cancelled"}

    def late(rows) -> float:
        return sum(r["is_late"] == "true" for r in rows) / len(rows)

    overall = late(shipments)
    kalimantan_nusa = [s for s in shipments if s["region_name"] == "Kalimantan Timur" and s["carrier"] == "NusaCargo"]
    assert late(kalimantan_nusa) > 0.25 > overall


def test_the_mcp_tool_matches_the_policy_and_rejects_bad_input() -> None:
    server = _load("late_delivery_server")
    risky = json.loads(server.assess_delivery_risk("Kalimantan Timur", "NusaCargo", "Regular", "Home & Living", 7))
    assert risky["band"] == "High" and "above 25%" in risky["policy_check"]
    calm = json.loads(server.assess_delivery_risk("DKI Jakarta", "FastExpress", "Regular", "Fashion"))
    assert calm["band"] == "Low" and calm["policy_check"] == "no action"
    assert "region_name must be one of" in json.loads(server.assess_delivery_risk("Mars", "FastExpress"))["error"]


def test_the_loader_literals_and_view() -> None:
    sys.modules.setdefault("trino", type(sys)("trino"))  # the loader only needs trino when it connects
    loader = _load("load_fulfillment_demo")
    assert loader.literal("it's", "VARCHAR") == "'it''s'"
    assert loader.literal("true", "BOOLEAN") == "TRUE" and loader.literal("2026-06-01", "DATE") == "DATE '2026-06-01'"
    assert "JOIN" in loader.VIEW and "order_id" in loader.VIEW

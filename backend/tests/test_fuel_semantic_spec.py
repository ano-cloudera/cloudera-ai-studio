"""The fuel distribution semantic model: every payload is one the Backend accepts, the expressions fit the tables, and the flow is right."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
import sqlglot

from app.api.v1 import semantic as semantic_api_models

ROOT = Path(__file__).resolve().parents[2]
SAMPLE = ROOT / "samples" / "fuel_distribution"
CONNECTOR = "11111111-1111-1111-1111-111111111111"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def build():
    sys.path.insert(0, str(ROOT / "scripts"))
    return _load("fuel_build_semantic_model", SAMPLE / "build_semantic_model.py")


@pytest.fixture(scope="module")
def columns() -> dict[str, set[str]]:
    sys.modules.setdefault("trino", type(sys)("trino"))  # the loader imports the Trino client only to connect
    loader = _load("fuel_loader", SAMPLE / "load_fuel_distribution.py")
    out = {table: {name for name, _ in cols} for table, (_, cols) in loader.TABLES.items()}
    select = sqlglot.parse_one(loader.VIEW.format(catalog="c", schema="s").split("AS\n", 1)[1], read="trino")
    out["v_fuel_quota_attainment"] = {e.alias_or_name for e in select.expressions}
    return out


def test_every_payload_is_accepted_by_the_backend_request_models(build) -> None:
    body = build.semantic_api.plan(build.SPEC, CONNECTOR)
    for item in body["entities"]:
        semantic_api_models.EntityCreateRequest.model_validate(item)
    for item in body["dimensions"]:
        semantic_api_models.DimensionCreateRequest.model_validate(item)
    for item in body["metrics"]:
        semantic_api_models.MetricCreateRequest.model_validate(item)
    for item in body["terms"]:
        semantic_api_models.TermCreateRequest.model_validate(item)


def test_keys_are_unique_every_reference_exists_and_nothing_lacks_a_description(build) -> None:
    body = build.semantic_api.plan(build.SPEC, CONNECTOR)
    entity_keys = {e["key"] for e in body["entities"]}
    for kind in ("entities", "dimensions", "metrics", "terms"):
        keys = [i["key"] for i in body[kind]]
        assert len(keys) == len(set(keys)), f"duplicate {kind} key"
    names = [m["name"].casefold() for m in body["metrics"]]
    assert len(names) == len(set(names))
    assert all(d["source_entity_key"] in entity_keys and d["description"] for d in body["dimensions"])
    assert all(m["source_entity_key"] in entity_keys and m["description"] and m["synonyms"] for m in body["metrics"])
    dimension_entity = {d["key"]: d["source_entity_key"] for d in body["dimensions"]}
    for metric in body["metrics"]:
        assert metric["allowed_dimension_keys"], metric["key"]
        assert all(dimension_entity[k] == metric["source_entity_key"] for k in metric["allowed_dimension_keys"])
    assert all(set(t["related_metric_keys"]) <= {m["key"] for m in body["metrics"]} for t in body["terms"])
    assert all(any(d["source_entity_key"] == key and d["data_type"] == "Date" for d in body["dimensions"]) for key in ("penyaluran", "kuota_subsidi"))


def test_a_synonym_belongs_to_one_metric(build) -> None:
    seen: dict[str, str] = {}
    for key, name, _, _, _, synonyms, _ in build.SPEC["metrics"]:
        for phrase in [name.split(" (")[0], *synonyms]:
            phrase = phrase.casefold()
            assert seen.setdefault(phrase, key) == key, f"'{phrase}' names both {seen[phrase]} and {key}"


def test_expressions_parse_as_trino_and_use_columns_that_exist(build, columns) -> None:
    table = {e["key"]: e["table"] for e in build.SPEC["entities"]}
    body = build.semantic_api.plan(build.SPEC, CONNECTOR)
    for metric in body["metrics"]:
        parsed = sqlglot.parse_one(f"SELECT {metric['expression']} FROM t", read="trino")
        used = {c.name for c in parsed.find_all(sqlglot.exp.Column)}
        assert used <= columns[table[metric["source_entity_key"]]], (metric["key"], used - columns[table[metric["source_entity_key"]]])
    for dim in body["dimensions"]:
        assert dim["source_column"] in columns[table[dim["source_entity_key"]]], dim["key"]


def test_the_flow_creates_validates_and_publishes_in_order(build, monkeypatch) -> None:
    calls: list[tuple[str, str]] = []

    def fake_call(self, method, path, body=None, *, ok_statuses=(200,)):
        calls.append((method, path))
        if path.startswith("/api/v1/connectors"):
            return {"connectors": [{"id": CONNECTOR, "name": "Trino"}]}
        if path.endswith("/semantic/models") and method == "GET":
            return {"models": []}
        if path.endswith("/semantic/models") and method == "POST":
            return {"model": {"id": "m1"}}
        if path.endswith("/versions") and method == "GET":
            return {"versions": [{"id": "v1", "version_number": 1}]}
        if path.endswith("/validate"):
            return {"valid": True, "errors": [], "warnings": []}
        if path.endswith("/publish-to-ask-data"):
            return {"status": "published"}
        return {}

    monkeypatch.setattr(build.semantic_api.Api, "call", fake_call)
    assert build.main(["--base-url", "https://example.invalid/token"]) == 0
    paths = [p for _, p in calls]
    order = [next(i for i, p in enumerate(paths) if p.endswith(suffix)) for suffix in ("/entities", "/dimensions", "/metrics", "/terms", "/validate", "/publish-to-ask-data")]
    assert order == sorted(order)
    assert len([p for p in paths if p.endswith("/metrics")]) == len(build.SPEC["metrics"])


def test_a_publish_that_needs_attention_is_a_failure(build, monkeypatch) -> None:
    def fake_call(self, method, path, body=None, *, ok_statuses=(200,)):
        if path.startswith("/api/v1/connectors"):
            return {"connectors": [{"id": CONNECTOR, "name": "Trino"}]}
        if path.endswith("/semantic/models") and method == "GET":
            return {"models": []}
        if path.endswith("/semantic/models") and method == "POST":
            return {"model": {"id": "m1"}}
        if path.endswith("/versions") and method == "GET":
            return {"versions": [{"id": "v1", "version_number": 1}]}
        if path.endswith("/publish-to-ask-data"):
            return {"detail": {"status": "needs_attention"}}
        return {}

    monkeypatch.setattr(build.semantic_api.Api, "call", fake_call)
    assert build.main(["--base-url", "https://example.invalid/token"]) == 1

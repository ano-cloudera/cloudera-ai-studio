"""The demo questions that are answered from one governed metric resolve to the metric the judge key names.

The artifact is built from the same spec the sample publishes, so a synonym that makes two metrics collide (the matcher then gives
up and asks a language model, which can pick wrongly) is caught here, without Trino or a model.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

from tests.test_unsupported_dimensions import _build, _field

ROOT = Path(__file__).resolve().parents[2]
SAMPLE = ROOT / "samples" / "fuel_distribution"


@pytest.fixture(scope="module")
def ctx():
    sys.path.insert(0, str(ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location("fuel_spec_for_resolution", SAMPLE / "build_semantic_model.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    spec_data = module.SPEC
    body = module.semantic_api.plan(spec_data, "x")
    datasets = []
    for entity in body["entities"]:
        fields = "".join(
            _field(d["key"], d["source_column"], d["name"], d["synonyms"], date=d["data_type"] == "Date")
            for d in body["dimensions"]
            if d["source_entity_key"] == entity["key"]
        )
        datasets.append((entity["key"], f'"{spec_data["catalog"]}"."{spec_data["schema"]}"."{entity["table_name"] or entity["view_name"]}"', fields))
    metrics = ""
    for m in body["metrics"]:
        extension = {"base_dataset": m["source_entity_key"], "allowed_dimensions": m["allowed_dimension_keys"], **((m.get("metadata") or {}).get("reference_extension") or {})}
        metrics += (
            f"  - name: {m['key']}\n    description: {json.dumps(m['description'])}\n    ai_context:\n      synonyms: {json.dumps(m['synonyms'])}\n"
            f"    expression:\n      dialects:\n        - dialect: ANSI_SQL\n          expression: {m['expression']}\n"
            f"    custom_extensions:\n      - vendor_name: REFERENCE\n        data: '{json.dumps(extension)}'\n"
        )
    return _build(datasets, metrics)


def _data_turns() -> list[tuple[str, str]]:
    turns = json.loads((SAMPLE / "judge_conversation.json").read_text())["turns"]
    return [(t["question"], t["expect"]["metric"][0]) for t in turns if t["expect"].get("route") == "data" and t["expect"].get("metric")]


@pytest.mark.parametrize(("question", "metric"), _data_turns())
def test_a_demo_question_resolves_to_its_metric_without_asking_a_model(ctx, question: str, metric: str) -> None:
    resolution = ctx.resolve(question)
    assert resolution["status"] == "resolved", (question, resolution.get("reason"))
    assert resolution["metric"] == metric


@pytest.mark.parametrize(
    ("question", "dimensions"),
    [
        ("Regional mana yang paling sering terlambat, dan seberapa jauh bedanya dengan yang lain?", ["regional"]),
        ("Bandingkan keterlambatan per tipe SPBU (COCO, CODO, DODO)", ["tipe_pelanggan"]),
        ("Produk apa yang volumenya paling besar?", ["produk"]),
        ("Bagaimana pencapaian kuota BBM subsidi per regional?", ["kuota_regional"]),
        ("Tampilkan volume penyaluran per provinsi", ["provinsi"]),
        ("Total volume per fuel terminal per bulan", ["tanggal_transaksi", "fuel_terminal"]),
    ],
)
def test_the_breakdown_a_demo_question_asks_for_is_kept(ctx, question: str, dimensions: list[str]) -> None:
    assert ctx.resolve(question)["dimensions"] == dimensions

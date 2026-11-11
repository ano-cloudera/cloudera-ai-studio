"""The language-model understanding: what the model reads is checked against the catalog, corrected once, and compiled from
the governed formula. The model is a fake that returns the readings a model would; the catalog is the fuel sample's own spec."""
from __future__ import annotations

import asyncio
import json

import pytest

from app.ask_data import understanding as u
from tests.test_fuel_resolution import ctx as fuel_ctx  # noqa: F401 - the fixture builds the model from the sample spec

VALUES = {
    ("penyaluran", "regional"): ["Jatimbalinus", "Jawa Bagian Barat", "Kalimantan", "Papua Maluku", "Sulawesi"],
    ("penyaluran", "fuel_terminal"): ["Kertapati", "Panjang", "Plumpang"],
    ("penyaluran", "tipe_pelanggan"): ["SPBU_COCO", "SPBU_CODO", "SPBU_DODO"],
    ("penyaluran", "produk"): ["Biosolar", "Pertalite", "Pertamax"],
    ("kuota_subsidi", "kuota_regional"): ["Kalimantan", "Papua Maluku", "Sulawesi"],
    ("kuota_subsidi", "kuota_produk"): ["Biosolar", "Pertalite"],
}


@pytest.fixture()
def ctx(fuel_ctx):  # noqa: F811
    return fuel_ctx


class Model:
    """Returns the given readings in turn and keeps what it was sent."""

    def __init__(self, *readings: dict) -> None:
        self.readings = list(readings)
        self.sent: list[list[dict]] = []

    async def generate_structured(self, messages, schema, **_):
        self.sent.append(list(messages))
        return schema.model_validate(self.readings.pop(0))


def _understand(ctx, model, question="q", **kwargs):
    return asyncio.run(u.understand(model, question=question, ctx=ctx, values=VALUES, **kwargs))


def test_the_model_sees_the_catalog_with_real_values_and_no_time_column_as_a_breakdown(ctx) -> None:
    catalog = u.build_catalog(ctx, VALUES)
    late = next(m for m in catalog["metrics"] if m["name"] == "tingkat_keterlambatan")
    assert "tanggal_transaksi" not in late["breakdowns"] and late["can_split_by_month"]
    terminal = next(d for d in catalog["dimensions"]["penyaluran"] if d["key"] == "fuel_terminal")
    assert terminal["name"] == "Terminal (TBBM)" and "Kertapati" in terminal["values"] and "tbbm" in terminal["synonyms"]


def test_a_valid_reading_becomes_the_resolution_without_a_second_call(ctx) -> None:
    model = Model({
        "metric": "total_volume", "breakdown": [], "by_month": True,
        "filters": [{"dimension": "fuel_terminal", "values": ["kertapati"]}],
        "period_start": "2025-07-01", "period_end": "2025-10-01", "language": "id",
    })
    resolution = _understand(ctx, model, "Volume Kertapati per bulan Juli sampai September 2025")
    assert len(model.sent) == 1
    assert resolution["status"] == "resolved" and resolution["metric"] == "total_volume"
    assert resolution["dimensions"] == ["tanggal_transaksi"]
    assert resolution["intent"]["filters"] == [{"dimension": "fuel_terminal", "values": ["Kertapati"]}]  # spelt as the data has it
    payload = json.loads(model.sent[0][1]["content"])
    assert payload["question"].startswith("Volume Kertapati") and payload["catalog"]["metrics"]


def test_an_invalid_reading_is_sent_back_once_with_what_was_wrong(ctx) -> None:
    wrong = {"metric": "pencapaian_kuota", "breakdown": ["fuel_terminal"], "language": "id"}
    fixed = {"metric": "pencapaian_kuota", "breakdown": ["kuota_regional"], "language": "id"}
    model = Model(wrong, fixed)
    resolution = _understand(ctx, model, "Pencapaian kuota per regional")
    assert len(model.sent) == 2
    assert "fuel_terminal" in model.sent[1][-1]["content"] and "kuota_regional" in model.sent[1][-1]["content"]
    assert resolution["dimensions"] == ["kuota_regional"]


def test_what_is_still_wrong_after_the_correction_is_left_out_and_said(ctx) -> None:
    reading = {
        "metric": "tingkat_keterlambatan", "breakdown": ["regional", "kuota_produk"],
        "filters": [{"dimension": "regional", "values": ["Papua Maluku", "Atlantis"]}], "language": "id",
    }
    resolution = _understand(ctx, Model(reading, reading))
    intent = resolution["intent"]
    assert resolution["dimensions"] == ["regional"]
    assert intent["filters"] == [{"dimension": "regional", "values": ["Papua Maluku"]}]
    assert any("kuota_produk" in n for n in intent["notes"]) and any("Atlantis" in n for n in intent["notes"])


def test_an_agent_step_keeps_the_metric_it_was_given(ctx) -> None:
    model = Model({"metric": "total_volume", "language": "id"}, {"metric": "total_volume", "language": "id"})
    resolution = _understand(ctx, model, pinned_metric="tingkat_keterlambatan")
    assert resolution["metric"] == "tingkat_keterlambatan"
    assert json.loads(model.sent[0][1]["content"])["metric_to_use"] == "tingkat_keterlambatan"


def test_no_fitting_metric_is_a_question_back_in_the_users_language(ctx) -> None:
    resolution = _understand(ctx, Model({"metric": "", "clarification": "Maksudnya volume atau nilai?", "language": "id"}))
    assert resolution["status"] == "needs_clarification" and resolution["question"] == "Maksudnya volume atau nilai?"


def test_a_bad_period_is_dropped_rather_than_guessed(ctx) -> None:
    reading = {"metric": "total_volume", "period_start": "2026-10-01", "period_end": None, "language": "en"}
    resolution = _understand(ctx, Model(reading, reading))
    assert resolution["intent"]["period_start"] is None and resolution["intent"]["period_end"] is None


def test_the_sql_is_compiled_from_the_governed_formula_and_the_intent(ctx) -> None:
    intent = {
        "breakdown": ["fuel_terminal"], "time_key": "tanggal_transaksi", "sort": "desc", "limit": None,
        "filters": [{"dimension": "regional", "values": ["Sumbagsel"]}], "period_start": "2025-07-01", "period_end": "2025-10-01",
    }
    sql = ctx.compile_intent("total_volume", intent, from_source='"iceberg"."default"."fuel_deliveries"')
    assert "SUM(volume_kl) AS metric_value" in sql
    assert "DATE_TRUNC('month'" in sql and "d.fuel_terminal AS fuel_terminal" in sql
    assert "d.regional = 'Sumbagsel'" in sql and "DATE '2025-07-01'" in sql and "DATE '2025-10-01'" in sql
    assert "ORDER BY DATE_TRUNC" in sql
    overall = ctx.compile_intent("total_volume", intent, from_source='"iceberg"."default"."fuel_deliveries"', overall=True)
    assert "GROUP BY" not in overall and "d.regional = 'Sumbagsel'" in overall and "DATE '2025-07-01'" in overall


def test_a_top_n_question_is_limited_and_a_lowest_one_sorted_up(ctx) -> None:
    sql = ctx.compile_intent("tingkat_keterlambatan", {"breakdown": ["regional"], "sort": "asc", "limit": 3})
    assert "ORDER BY metric_value ASC" in sql and sql.rstrip().endswith("LIMIT 3")


def test_the_compiled_sql_passes_the_governed_sql_check(ctx) -> None:
    from app.ask_data.validation import validate_ask_data_sql

    intent = {"breakdown": ["kuota_regional"], "time_key": None, "filters": [{"dimension": "kuota_produk", "values": ["Biosolar"]}], "period_start": "2026-10-01", "period_end": "2026-11-01"}
    source = '"iceberg"."default"."v_fuel_quota_attainment"'
    sql = ctx.compile_intent("pencapaian_kuota", intent, from_source=source)
    state = {
        "datasource_context": {
            "legacy_fallback": False, "connector_id": "00000000-0000-0000-0000-000000000001", "connector_type": "trino", "connector_name": "t",
            "dialect": "trino", "semantic_version_id": "00000000-0000-0000-0000-000000000002", "semantic_entity_keys": ["kuota_subsidi"],
            "qualified_sources": {"kuota_subsidi": source}, "allowed_physical_tables": ["iceberg.default.v_fuel_quota_attainment"],
        },
        "semantic_resolution": {"status": "resolved", "metric": "pencapaian_kuota", "dimensions": ["kuota_regional"]},
    }
    checked = validate_ask_data_sql(sql, ctx, state=state)
    assert checked.valid, checked.error


def test_a_breakdown_by_the_dimension_filtered_to_one_value_is_sent_back(ctx) -> None:
    one_row = {"metric": "tingkat_keterlambatan", "breakdown": ["regional"], "filters": [{"dimension": "regional", "values": ["Papua Maluku"]}], "language": "id"}
    fixed = {"metric": "tingkat_keterlambatan", "breakdown": ["fuel_terminal"], "filters": [{"dimension": "regional", "values": ["Papua Maluku"]}], "language": "id"}
    model = Model(one_row, fixed)
    resolution = _understand(ctx, model, "Keterlambatan di Papua Maluku per terminal")
    assert len(model.sent) == 2 and "single row" in model.sent[1][-1]["content"]
    assert resolution["dimensions"] == ["fuel_terminal"]


def test_comparing_some_values_of_the_breakdown_dimension_is_allowed(ctx) -> None:
    two = {"metric": "tingkat_keterlambatan", "breakdown": ["regional"], "filters": [{"dimension": "regional", "values": ["Papua Maluku", "Kalimantan"]}], "language": "id"}
    model = Model(two)
    resolution = _understand(ctx, model, "Bandingkan keterlambatan Papua Maluku dan Kalimantan")
    assert len(model.sent) == 1 and resolution["dimensions"] == ["regional"]

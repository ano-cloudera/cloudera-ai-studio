"""A breakdown is recognised by the dimension's name and synonyms, and one a metric cannot do is said so instead of dropped."""
from __future__ import annotations

import json
import pathlib
import tempfile

import pytest

from app.ask_data.intent_satisfaction import infer_dimensions_from_question
from app.semantic.context import SemanticContextService


def _field(key: str, column: str, display: str, synonyms: list[str], *, date: bool = False) -> str:
    out = f"      - name: {key}\n        datatype: {'Date' if date else 'String'}\n        expression:\n          dialects:\n            - dialect: ANSI_SQL\n              expression: {column}\n"
    if date:
        out += "        dimension:\n          is_time: true\n"
    else:
        out += "        dimension: {}\n"
    return out + f"        ai_context:\n          display_name: {json.dumps(display)}\n          synonyms: {json.dumps(synonyms)}\n"


def _metric(key: str, description: str, expression: str, synonyms: list[str], dataset: str, dims: list[str]) -> str:
    extension = json.dumps({"base_dataset": dataset, "allowed_dimensions": dims})
    return (
        f"  - name: {key}\n    description: {json.dumps(description)}\n    ai_context:\n      synonyms: {json.dumps(synonyms)}\n"
        f"    expression:\n      dialects:\n        - dialect: ANSI_SQL\n          expression: {expression}\n"
        f"    custom_extensions:\n      - vendor_name: REFERENCE\n        data: '{extension}'\n"
    )


def _build(datasets: list[tuple[str, str, str]], metrics: str) -> SemanticContextService:
    root = pathlib.Path(tempfile.mkdtemp()) / "rt"
    ossie = root / "ossie"
    ossie.mkdir(parents=True)
    body = "".join(f"  - name: {name}\n    source: '{source}'\n    primary_key: [id]\n    fields:\n{fields}" for name, source, fields in datasets)
    (ossie / "reference_core.ossie.yaml").write_text(f'version: "0.2.0.dev0"\nname: m\ndescription: x\ndatasets:\n{body}metrics:\n{metrics}')
    (ossie / "reference_governance.yaml").write_text('unknown_metric_question: "Which?"\n')
    (ossie / "golden_questions.yaml").write_text("questions: []\n")
    return SemanticContextService(root, validate_profile=False)


@pytest.fixture(scope="module")
def fuel() -> SemanticContextService:
    deliveries_dims = ["tanggal_transaksi", "regional", "provinsi", "fuel_terminal", "tipe_pelanggan", "kode_pelanggan"]
    quota_dims = ["kuota_bulan", "kuota_regional", "kuota_produk"]
    deliveries = (
        _field("tanggal_transaksi", "tanggal_transaksi", "Tanggal Transaksi", ["bulan"], date=True)
        + _field("regional", "regional", "Regional", ["region"])
        + _field("provinsi", "provinsi", "Provinsi", ["wilayah", "daerah"])
        + _field("fuel_terminal", "fuel_terminal", "Terminal (TBBM)", ["depot"])
        + _field("tipe_pelanggan", "nama_tipe_pelanggan", "Tipe Pelanggan", ["tipe spbu", "jenis spbu"])
        + _field("kode_pelanggan", "kode_pelanggan", "SPBU", ["kode spbu"])
    )
    quota = (
        _field("kuota_bulan", "bulan", "Bulan Kuota", [], date=True)
        + _field("kuota_regional", "regional", "Regional (Kuota)", ["wilayah kuota"])
        + _field("kuota_produk", "produk", "Produk Subsidi", [])
    )
    metrics = (
        _metric("total_volume", "Total BBM disalurkan, KL.", "SUM(volume_kl)", ["volume", "penyaluran"], "penyaluran", deliveries_dims)
        + _metric("tingkat_keterlambatan", "Persentase LO terlambat.", "COUNT(*)", ["keterlambatan", "telat"], "penyaluran", deliveries_dims)
        + _metric("pencapaian_kuota", "Realisasi dibagi kuota.", "SUM(realisasi_kl) * 100.0 / SUM(kuota_kl)", ["pencapaian kuota", "quota attainment", "kuota"], "kuota", quota_dims)
    )
    return _build([("penyaluran", '"iceberg"."default"."fuel_deliveries"', deliveries), ("kuota", '"iceberg"."default"."v_fuel_quota"', quota)], metrics)


@pytest.fixture(scope="module")
def retail() -> SemanticContextService:
    transactions = _field("txn_date", "txn_date", "Transaction Date", [], date=True) + _field("product_category", "product_category", "Product Category", ["kategori produk"])
    customers = _field("loyalty_tier", "loyalty_tier", "Loyalty Tier", ["tier"]) + _field("customer_region", "region_name", "Region", ["wilayah"])
    metrics = (
        _metric("total_revenue", "Net amount paid.", "SUM(amount)", ["revenue", "pendapatan", "penjualan"], "transactions", ["txn_date", "product_category"])
        + _metric("customer_revenue", "Total net spend of the customers in the group.", "SUM(total_spend)", ["pendapatan per tier", "spend by segment"], "customers", ["loyalty_tier", "customer_region"])
    )
    return _build([("transactions", '"c"."s"."t"', transactions), ("customers", '"c"."s"."v"', customers)], metrics)


def _infer(ctx: SemanticContextService, metric: str, question: str) -> list[str]:
    definition = ctx.metric_definition(metric)
    return infer_dimensions_from_question(question, set(definition["allowed_dimensions"]), dataset_name=definition["base_dataset"], registry=ctx.registry)


def test_a_dimension_is_found_by_its_name_synonyms_and_alias(fuel) -> None:
    assert _infer(fuel, "total_volume", "Total volume per provinsi") == ["provinsi"]
    assert _infer(fuel, "total_volume", "Volume per wilayah") == ["provinsi"]
    assert _infer(fuel, "total_volume", "Volume per TBBM") == ["fuel_terminal"]
    assert _infer(fuel, "total_volume", "Volume per regional dan terminal") == ["regional", "fuel_terminal"]
    assert _infer(fuel, "tingkat_keterlambatan", "Regional mana yang paling sering telat?") == ["regional"]


def test_the_longest_name_wins_so_station_type_is_not_the_station(fuel) -> None:
    assert _infer(fuel, "tingkat_keterlambatan", "Bandingkan keterlambatan per tipe SPBU") == ["tipe_pelanggan"]
    assert _infer(fuel, "tingkat_keterlambatan", "Keterlambatan per SPBU") == ["kode_pelanggan"]


def test_a_supported_breakdown_resolves_as_before(fuel) -> None:
    resolution = fuel.resolve("Pencapaian kuota per regional")
    assert resolution["status"] == "resolved" and resolution["metric"] == "pencapaian_kuota"
    assert resolution["dimensions"] == ["kuota_regional"] and not resolution["dimension_mismatch"]


def test_a_breakdown_the_metric_cannot_do_is_said_plainly(fuel) -> None:
    resolution = fuel.resolve("Berapa pencapaian kuota per terminal?")
    assert resolution["status"] == "needs_clarification" and resolution["reason"] == "unsupported_dimension"
    text = resolution["question"]
    assert "Terminal (TBBM)" in text and "Regional (Kuota)" in text and "belum bisa dipecah" in text
    english = fuel.resolve("What is the quota attainment by terminal?")
    assert english["status"] == "needs_clarification" and "cannot be broken down" in english["question"]


def test_a_partly_supported_breakdown_keeps_what_works_and_notes_the_rest(fuel) -> None:
    resolution = fuel.resolve("Pencapaian kuota per regional dan terminal")
    assert resolution["status"] == "resolved"
    assert resolution["dimensions"] == ["kuota_regional"]
    assert resolution["dimension_mismatch"] == ["Terminal (TBBM)"]


def test_the_metric_that_can_do_the_breakdown_is_used_when_the_words_point_to_it(retail) -> None:
    resolution = retail.resolve("Pendapatan per loyalty tier")
    assert resolution["status"] == "resolved"
    assert resolution["metric"] == "customer_revenue" and resolution["dimensions"] == ["loyalty_tier"]
    kept = retail.resolve("Pendapatan per kategori produk")
    assert kept["metric"] == "total_revenue" and kept["dimensions"] == ["product_category"]

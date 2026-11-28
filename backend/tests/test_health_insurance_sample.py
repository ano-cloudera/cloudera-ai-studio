"""The health insurance sample: the data carries its planted patterns, the example model flags them with readable reasons, the scoring
service answers like the contract says, and the warehouse SQL is what the loader runs. A small data set in a temporary folder."""
from __future__ import annotations

import csv
import importlib.util
import sys
from collections import Counter
from pathlib import Path

import pytest

SAMPLE = Path(__file__).resolve().parents[2] / "samples" / "health_insurance"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def data(tmp_path_factory):
    out = tmp_path_factory.mktemp("health_insurance")
    generator = _load("health_insurance_generate_data", SAMPLE / "generate_data.py")
    generator.OUT = out
    assert generator.main(["--claims", "60000", "--members", "30000"]) == 0
    return out


def _rows(folder: Path, name: str) -> list[dict]:
    with (folder / name).open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def test_every_pattern_is_planted_and_every_name_is_fictional(data) -> None:
    truth = Counter(r["pola"] for r in _rows(data, "ground_truth.csv"))
    assert set(truth) == {"upcoding", "jaringan", "volume_dokter", "lama_rawat", "klaim_ganda", "rawat_ulang"}
    providers = _rows(data, "penyedia.csv")
    assert all(" Demo " in p["nama_penyedia"] for p in providers)
    claims = _rows(data, "klaim.csv")
    ring = {r["id_klaim"] for r in _rows(data, "ground_truth.csv") if r["pola"] == "jaringan"}
    accounts = {c["rekening_penggantian_hash"] for c in claims if c["id_klaim"] in ring}
    assert len(accounts) == 6 and all(c["metode_klaim"] == "Reimbursement" for c in claims if c["id_klaim"] in ring)
    assert {c["status_klaim"] for c in claims} == {"Dibayar", "Ditolak", "Diproses"}


def test_the_generator_is_deterministic(data, tmp_path) -> None:
    generator = _load("health_insurance_generate_data_again", SAMPLE / "generate_data.py")
    generator.OUT = tmp_path
    generator.main(["--claims", "60000", "--members", "30000"])
    assert (tmp_path / "klaim.csv").read_bytes() == (data / "klaim.csv").read_bytes()


@pytest.fixture(scope="module")
def scoring(data):
    sys.path.insert(0, str(SAMPLE / "scoring"))
    model = _load("model", SAMPLE / "scoring" / "model.py")
    model.DATA = data
    service = _load("health_insurance_service", SAMPLE / "scoring" / "service.py")
    service.read = model.read
    return model, service


def test_the_example_model_flags_the_ring_with_its_own_figures(data, scoring) -> None:
    model, _ = scoring
    scorer = model.Model.load()
    context = model.new_context(scorer.spec)
    truth = {r["id_klaim"]: r["pola"] for r in _rows(data, "ground_truth.csv")}
    ring_scores, normal_alerts, normal = [], 0, 0
    reasons: list[str] = []
    for claim in model.arrival_order(_rows(data, "klaim.csv")):
        values, facts = context.features(claim)
        context.remember(claim)
        result = scorer.score(values, facts)
        if truth.get(claim["id_klaim"]) == "jaringan":
            ring_scores.append(result["skor_fraud"])
            reasons += result["alasan"]
        elif claim["id_klaim"] not in truth:
            normal += 1
            normal_alerts += result["skor_fraud"] >= scorer.alert_at
    assert sum(s >= scorer.alert_at for s in ring_scores) / len(ring_scores) > 0.9
    assert normal_alerts / normal < 0.01
    assert any(r.startswith("Rekening penggantian dipakai") and "peserta berbeda" in r for r in reasons)


def test_the_service_scores_once_and_refuses_an_incomplete_claim(data, scoring) -> None:
    _, service = scoring
    scorer = service.Scorer()
    claim = next(c for c in _rows(data, "klaim.csv") if c["metode_klaim"] == "Cashless")
    fresh = {**claim, "id_klaim": "KLM-9999999"}
    first = scorer.score(fresh)
    again = scorer.score(fresh)
    assert first == again and set(first) >= {"skor_fraud", "tingkat_risiko", "alasan", "versi_model", "alert"}
    with pytest.raises(ValueError, match="missing"):
        scorer.score({"id_klaim": "KLM-1"})


def test_the_claims_table_is_partitioned_by_month_on_iceberg_only() -> None:
    warehouse = _load("health_insurance_warehouse", SAMPLE / "warehouse.py")
    iceberg = warehouse.create_table_sql('"iceberg"."demo"', "hi_klaim", True)
    plain = warehouse.create_table_sql('"memory"."demo"', "hi_klaim", False)
    assert "partitioning = ARRAY['month(tanggal_masuk)']" in iceberg and "format = 'PARQUET'" in iceberg
    assert "WITH" not in plain
    assert warehouse.literal("O'Brien", "VARCHAR") == "'O''Brien'" and warehouse.literal("", "BIGINT") == "NULL"


def test_the_scoring_service_starts_when_the_application_script_runs_in_a_kernel_without___file__(monkeypatch) -> None:
    """Cloudera AI runs an Application script in a kernel cell, where __file__ is not defined: the service finds itself from the working directory."""
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    monkeypatch.chdir(root)
    monkeypatch.setattr(sys, "path", list(sys.path))
    source = (root / "samples" / "health_insurance" / "scoring" / "service.py").read_text()
    namespace: dict = {"__name__": "kernel_cell"}  # no __file__, and not "__main__": the server is not started
    exec(compile(source, "<cell>", "exec"), namespace)  # noqa: S102 - the repo's own file
    assert namespace["HERE"] == root / "samples" / "health_insurance" / "scoring"
    assert callable(namespace["main"])


def _warehouse():
    return _load("hi_warehouse_for_stream_tests", SAMPLE / "warehouse.py")


def test_the_tables_the_stream_fills_have_the_columns_of_the_history_they_are_added_to() -> None:
    tables = _warehouse().TABLES
    assert tables["hi_klaim_baru"][1] == tables["hi_klaim"][1] and tables["hi_klaim_baru"][2] == tables["hi_klaim"][2]  # same columns, same partitioning
    assert tables["hi_alert_baru"][1] == tables["hi_alert"][1]
    assert tables["hi_klaim_baru"][0] is None and tables["hi_alert_baru"][0] is None  # no csv: only the stream fills them


def test_every_view_reads_only_tables_and_views_that_come_before_it_and_the_combined_ones_add_the_stream() -> None:
    import re

    warehouse = _warehouse()
    known = set(warehouse.TABLES)
    for view in warehouse.VIEW_ORDER:
        sql = warehouse.create_view_sql("c.s", view)
        read = set(re.findall(r"c\.s\.(\w+)", sql)) - {view}
        assert read <= known, f"{view} reads {sorted(read - known)} before they exist"
        known.add(view)
    combined = warehouse.create_view_sql("c.s", "v_hi_klaim_gabungan")
    assert "c.s.hi_klaim\n" in combined and "c.s.hi_klaim_baru" in combined and "UNION ALL" in combined
    for view in ("v_hi_klaim", "v_hi_alert", "v_hi_rasio_klaim"):  # the views the analysis reads never go around the combined ones
        sql = warehouse.create_view_sql("c.s", view)
        assert "c.s.hi_klaim " not in sql and "c.s.hi_klaim\n" not in sql and "c.s.hi_alert " not in sql


def test_the_latency_script_reads_the_creation_time_in_a_generated_claim_id() -> None:
    latency = _load("hi_measure_latency", SAMPLE / "nifi" / "measure_latency.py")
    created = latency.claim_time("KLM-N26112814112769686")
    assert (created.year, created.month, created.day, created.hour, created.minute, created.second) == (2026, 11, 28, 14, 11, 27)
    assert latency.claim_time("KLM-F261128141129095") is not None
    assert latency.claim_time("KLM-0000003") is None  # a claim of the history has no creation time in its id


def test_the_exported_nifi_flow_holds_no_secret_and_no_identifier_of_the_environment_it_came_from() -> None:
    import json

    text = (SAMPLE / "nifi" / "flow" / "insurance_claims_demo.json").read_text()
    flow = json.loads(text)["flowContents"]
    assert {p["name"] for p in flow["processors"]} >= {"Generate Claim", "Generate Fraud Claim", "Score Claim", "Write Claims to Iceberg", "Write Alerts to Iceberg"}
    assert "Bearer <SCORING_API_KEY>" in text and "<workload-user>" in text and "<datalake-bucket>" in text
    for private in ("cloudera.site", "ano03", "981304421142", "triano"):
        assert private not in text, private

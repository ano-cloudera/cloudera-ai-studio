"""The answer key in samples/fuel_distribution/judge_conversation.json matches the data, so a wrong key cannot fail a right answer."""
from __future__ import annotations

import csv
import importlib.util
import json
from collections import defaultdict
from pathlib import Path

SAMPLE = Path(__file__).resolve().parents[2] / "samples" / "fuel_distribution"


def _generator():
    spec = importlib.util.spec_from_file_location("fuel_generate_for_key", SAMPLE / "generate_data.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_judge_numbers_come_from_the_data(tmp_path) -> None:
    _generator().generate(_generator().ROWS, tmp_path)
    deliveries = list(csv.DictReader((tmp_path / "deliveries.csv").open()))
    quota = list(csv.DictReader((tmp_path / "quota.csv").open()))
    customers = list(csv.DictReader((tmp_path / "customers.csv").open()))
    done = [d for d in deliveries if d["status_pengiriman"] != "Dalam_Perjalanan"]

    def late(rows) -> float:
        return round(sum(r["status_pengiriman"] == "Terlambat" for r in rows) * 100 / len(rows), 2)

    def volume(rows) -> int:
        return sum(int(r["volume_kl"]) for r in rows)

    facts = {
        "total volume": (volume(deliveries), 4996168),
        "late overall": (late(done), 16.07),
        "late Papua Maluku": (late([d for d in done if d["regional"] == "Papua Maluku"]), 34.54),
        "late DODO": (late([d for d in done if d["nama_tipe_pelanggan"] == "SPBU_DODO"]), 19.53),
        "late CODO": (late([d for d in done if d["nama_tipe_pelanggan"] == "SPBU_CODO"]), 14.95),
        "late COCO": (late([d for d in done if d["nama_tipe_pelanggan"] == "SPBU_COCO"]), 9.22),
        "Pertalite volume": (volume([d for d in deliveries if d["produk"] == "Pertalite"]), 1530928),
        "subsidised share": (round(volume([d for d in deliveries if d["kategori_bbm"] == "Subsidi"]) * 100 / volume(deliveries), 2), 49.78),
        "SPBU": (sum(c["segmen_bisnis"] == "Ritel_SPBU" for c in customers), 3000),
        "Kertapati Aug 2025 KL": (volume([d for d in deliveries if d["fuel_terminal"] == "Kertapati" and d["tanggal_transaksi"].startswith("2025-08")]), 2056),
    }
    province = defaultdict(int)
    for d in deliveries:
        province[d["provinsi"]] += int(d["volume_kl"])
    top = max(province, key=province.get)
    facts["top province"] = (top, "Jawa Tengah")
    facts["top province KL"] = (province[top], 714496)

    realised: dict[tuple, int] = defaultdict(int)
    for d in deliveries:
        if d["segmen_bisnis"] == "Ritel_SPBU" and d["produk"] in ("Pertalite", "Biosolar"):
            realised[(d["regional"], d["produk"], d["tanggal_transaksi"][:7] + "-01")] += int(d["volume_kl"])
    given: dict[tuple, int] = defaultdict(int)
    for q in quota:
        given[(q["regional"], q["produk"], q["bulan"])] += int(q["kuota_kl"])
    by_region: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for key, kl in given.items():
        by_region[key[0]][0] += realised.get(key, 0)
        by_region[key[0]][1] += kl
    attainment = {region: round(a * 100 / b, 2) for region, (a, b) in by_region.items()}
    facts["quota top regional"] = (max(attainment, key=attainment.get), "Kalimantan")
    facts["quota Kalimantan"] = (round(attainment["Kalimantan"], 1), 101.9)
    facts["quota Papua Maluku"] = (round(attainment["Papua Maluku"], 1), 80.7)
    key = ("Sulawesi", "Biosolar", "2026-10-01")
    facts["Biosolar Sulawesi Oct 2026"] = (round(realised[key] * 100 / given[key], 2), 114.74)

    for name, (seen, wanted) in facts.items():
        assert seen == wanted, f"{name}: data says {seen}, the key says {wanted}"

    keyed = json.loads((SAMPLE / "judge_conversation.json").read_text())
    assert keyed["language"] == "id" and len(keyed["turns"]) >= 15
    assert all(t["question"] and t["expect"] for t in keyed["turns"])
    numbers = {float(n) for t in keyed["turns"] for n in (t["expect"].get("numbers") or [])}
    assert {16.07, 34.54, 19.53, 49.78, 114.74} <= numbers


def test_the_paraphrase_key_comes_from_the_data(tmp_path) -> None:
    _generator().generate(_generator().ROWS, tmp_path)
    deliveries = list(csv.DictReader((tmp_path / "deliveries.csv").open()))
    done = [d for d in deliveries if d["status_pengiriman"] != "Dalam_Perjalanan"]

    def late(rows) -> float:
        return round(sum(r["status_pengiriman"] == "Terlambat" for r in rows) * 100 / len(rows), 2)

    by_region = defaultdict(list)
    by_terminal = defaultdict(list)
    for d in done:
        by_region[d["regional"]].append(d)
        if d["regional"] == "Papua Maluku":
            by_terminal[d["fuel_terminal"]].append(d)
    lowest = min(by_region, key=lambda r: late(by_region[r]))
    assert (lowest, late(by_region[lowest])) == ("Jatimbalinus", 11.4)
    worst = max(by_terminal, key=lambda t: late(by_terminal[t]))
    assert (worst, late(by_terminal[worst])) == ("Sorong", 36.31)
    assert round(sum(int(d["durasi_kirim_menit"]) for d in done) / len(done), 2) == 168.54
    assert sum(int(d["total_nilai_idr"]) for d in deliveries) == 58537828400000
    months_2025 = {d["tanggal_transaksi"][:7] for d in deliveries if d["fuel_terminal"] == "Kertapati" and d["tanggal_transaksi"].startswith("2025")}
    assert len(months_2025) == 12
    keyed = json.loads((SAMPLE / "judge_paraphrases.json").read_text())
    assert len(keyed["turns"]) == 16 and all(t["expect"].get("route") == "data" for t in keyed["turns"])

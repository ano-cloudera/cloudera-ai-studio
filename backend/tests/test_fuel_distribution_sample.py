"""The fuel distribution sample: reproducible, internally consistent, and the planted patterns are there."""
from __future__ import annotations

import csv
import importlib.util
from collections import defaultdict
from pathlib import Path

SAMPLE = Path(__file__).resolve().parents[2] / "samples" / "fuel_distribution"


def _generator():
    spec = importlib.util.spec_from_file_location("fuel_generate_data", SAMPLE / "generate_data.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_generation_is_reproducible(tmp_path) -> None:
    generator = _generator()
    generator.generate(3000, tmp_path / "a")
    generator.generate(3000, tmp_path / "b")
    for name in ("customers.csv", "deliveries.csv"):
        assert (tmp_path / "a" / name).read_bytes() == (tmp_path / "b" / name).read_bytes()


def test_the_data_is_consistent_and_the_patterns_are_planted(tmp_path) -> None:
    generator = _generator()
    generator.generate(30000, tmp_path)
    customers = list(csv.DictReader((tmp_path / "customers.csv").open()))
    deliveries = list(csv.DictReader((tmp_path / "deliveries.csv").open()))

    codes = [c["kode_pelanggan"] for c in customers]
    assert len(codes) == len(set(codes))
    assert {d["kode_pelanggan"] for d in deliveries} <= set(codes)
    assert len({d["id_lo"] for d in deliveries}) == len(deliveries)

    assert all(float(d["volume_kl"]) <= float(d["kapasitas_tangki_kl"]) for d in deliveries)
    assert all(d["total_nilai_idr"] == str(int(d["volume_kl"]) * 1000 * int(d["harga_per_liter_idr"])) for d in deliveries)
    assert all(d["produk"] != "Avtur" or "Penerbangan" in d["nama_tipe_pelanggan"] for d in deliveries)
    for d in deliveries:
        if d["status_pengiriman"] == "Dalam_Perjalanan":
            assert d["durasi_kirim_menit"] == "" and d["tanggal_transaksi"] == "2026-10-31"
        else:
            assert (d["status_pengiriman"] == "Terlambat") == (int(d["durasi_kirim_menit"]) > int(d["sla_menit"]))

    def late(rows) -> float:
        return sum(r["status_pengiriman"] == "Terlambat" for r in rows) / len(rows)

    done = [d for d in deliveries if d["status_pengiriman"] != "Dalam_Perjalanan"]
    by_region = defaultdict(list)
    for d in done:
        by_region[d["regional"]].append(d)
    assert late(by_region["Papua Maluku"]) > late(by_region["Kalimantan"]) > 1.5 * late(by_region["Jawa Bagian Barat"])
    retail = [d for d in done if d["segmen_bisnis"] == "Ritel_SPBU"]
    assert late([d for d in retail if d["nama_tipe_pelanggan"] == "SPBU_DODO"]) > late([d for d in retail if d["nama_tipe_pelanggan"] == "SPBU_COCO"])
    subsidi = sum(int(d["volume_kl"]) for d in retail if d["kategori_bbm"] == "Subsidi")
    assert 0.55 < subsidi / sum(int(d["volume_kl"]) for d in retail) < 0.8

    per_month = defaultdict(int)
    for d in deliveries:
        per_month[d["tanggal_transaksi"][:7]] += 1
    assert per_month["2025-03"] > 1.2 * per_month["2025-04"] and per_month["2025-12"] > 1.2 * per_month["2025-11"]
    kertapati = lambda month: sum(1 for d in deliveries if d["fuel_terminal"] == "Kertapati" and d["tanggal_transaksi"].startswith(month))  # noqa: E731
    assert kertapati("2025-08") < 0.5 * kertapati("2025-07")


def test_every_late_order_has_a_reason_and_the_reasons_follow_the_route(tmp_path) -> None:
    from collections import Counter

    generator = _generator()
    generator.generate(60000, tmp_path)
    deliveries = list(csv.DictReader((tmp_path / "deliveries.csv").open()))
    for d in deliveries:
        assert bool(d["alasan_keterlambatan"]) == (d["status_pengiriman"] == "Terlambat")
        assert not d["alasan_keterlambatan"] or d["alasan_keterlambatan"] in generator.REASONS

    def top(rows) -> str:
        return Counter(r["alasan_keterlambatan"] for r in rows if r["alasan_keterlambatan"]).most_common(1)[0][0]

    assert top(d for d in deliveries if d["fuel_terminal"] == "Wayame") == "Cuaca buruk"
    assert top(d for d in deliveries if d["fuel_terminal"] in ("Jayapura", "Sorong", "Tanjung Batu")) == "Akses jalan rusak"
    assert top(d for d in deliveries if d["regional"] == "Jawa Bagian Barat") in ("Kemacetan lalu lintas", "Antrean muat di TBBM")
    detour = [d for d in deliveries if d["fuel_terminal"] == "Panjang" and d["provinsi"] != "Lampung"]
    assert detour and top(detour) == "Pasokan dari terminal alternatif"

    def minutes_late(reason: str) -> float:
        late = [int(d["durasi_kirim_menit"]) - int(d["sla_menit"]) for d in deliveries if d["alasan_keterlambatan"] == reason]
        return sum(late) / len(late)

    assert minutes_late("Akses jalan rusak") > minutes_late("Kemacetan lalu lintas")


def test_the_reason_is_the_last_column_so_the_other_columns_keep_their_place(tmp_path) -> None:
    """The reason is appended after the existing columns; the values of the others are unchanged (drawn on their own stream)."""
    generator = _generator()
    generator.generate(5000, tmp_path)
    rows = list(csv.DictReader((tmp_path / "deliveries.csv").open()))
    assert rows[0].keys() >= {"alasan_keterlambatan", "status_pengiriman"}
    assert list(rows[0].keys())[-1] == "alasan_keterlambatan"

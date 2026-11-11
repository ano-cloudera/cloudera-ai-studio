#!/usr/bin/env python3
"""Print the correct answer to the demo questions, computed from the CSVs (the key for judge_conversation.json).

Usage: python samples/fuel_distribution/expected_answers.py
"""
from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

DATA = Path(__file__).resolve().parent / "data"


def rows(name: str) -> list[dict]:
    return list(csv.DictReader((DATA / f"{name}.csv").open()))


def pct(a: float, b: float) -> float:
    return round(a * 100 / b, 2) if b else 0.0


def main() -> None:
    deliveries, customers, quota = rows("deliveries"), rows("customers"), rows("quota")
    done = [d for d in deliveries if d["status_pengiriman"] != "Dalam_Perjalanan"]
    late = lambda rs: pct(sum(r["status_pengiriman"] == "Terlambat" for r in rs), len(rs))  # noqa: E731
    vol = lambda rs: sum(int(r["volume_kl"]) for r in rs)  # noqa: E731

    print(f"Total volume: {vol(deliveries):,} KL; LO: {len(deliveries):,}; value IDR {sum(int(d['total_nilai_idr']) for d in deliveries):,}")
    print(f"Late rate overall: {late(done)}% over {len(done):,} finished LO; on time {round(100 - late(done), 2)}%")
    print(f"Late LO: {sum(d['status_pengiriman'] == 'Terlambat' for d in done):,}; average delivery minutes {sum(int(d['durasi_kirim_menit']) for d in done) / len(done):.1f}")
    for key, title in (("regional", "Late rate by regional"), ("nama_tipe_pelanggan", "Late rate by customer type"), ("fuel_terminal", "Late rate by terminal (top 5)")):
        groups = defaultdict(list)
        for d in done:
            groups[d[key]].append(d)
        ranked = sorted(groups.items(), key=lambda kv: -late(kv[1]))
        shown = ranked[:5] if "top 5" in title else ranked
        print(f"{title}: " + ", ".join(f"{k} {late(v)}" for k, v in shown if k.startswith(("SPBU", "Papua", "Kal", "Sul", "Sumbag", "Jawa", "Jatim")) or "top 5" in title))
    dist = defaultdict(list)
    for d in deliveries:
        dist[d["regional"]].append(float(d["jarak_tempuh_km"]))
    print("Average distance km by regional: " + ", ".join(f"{k} {sum(v) / len(v):.1f}" for k, v in sorted(dist.items(), key=lambda kv: -sum(kv[1]) / len(kv[1]))))
    prod = defaultdict(int)
    for d in deliveries:
        prod[d["produk"]] += int(d["volume_kl"])
    print("Volume by product: " + ", ".join(f"{k} {v:,}" for k, v in sorted(prod.items(), key=lambda kv: -kv[1])[:4]))
    print(f"Subsidised share of all volume: {pct(vol([d for d in deliveries if d['kategori_bbm'] == 'Subsidi']), vol(deliveries))}%")
    region_vol = defaultdict(int)
    for d in deliveries:
        region_vol[d["regional"]] += int(d["volume_kl"])
    print("Volume by regional: " + ", ".join(f"{k} {v:,}" for k, v in sorted(region_vol.items(), key=lambda kv: -kv[1])[:3]))
    prov_vol = defaultdict(int)
    for d in deliveries:
        prov_vol[d["provinsi"]] += int(d["volume_kl"])
    top = sorted(prov_vol.items(), key=lambda kv: -kv[1])
    print(f"Provinces: {len(prov_vol)}; top 3 by volume: " + ", ".join(f"{k} {v:,}" for k, v in top[:3]))
    kert = defaultdict(int)
    for d in deliveries:
        if d["fuel_terminal"] in ("Kertapati", "Panjang") and d["tanggal_transaksi"][:7] in ("2025-07", "2025-08", "2025-09"):
            kert[(d["fuel_terminal"], d["tanggal_transaksi"][:7])] += int(d["volume_kl"])
    print("Kertapati/Panjang KL: " + ", ".join(f"{t} {m} {v:,}" for (t, m), v in sorted(kert.items())))
    realised = defaultdict(int)
    for d in deliveries:
        if d["segmen_bisnis"] == "Ritel_SPBU" and d["produk"] in ("Pertalite", "Biosolar"):
            realised[(d["regional"], d["produk"], d["tanggal_transaksi"][:7] + "-01")] += int(d["volume_kl"])
    given = defaultdict(int)
    for q in quota:
        given[(q["regional"], q["produk"], q["bulan"])] += int(q["kuota_kl"])
    by_region = defaultdict(lambda: [0, 0])
    for key, kl in given.items():
        by_region[key[0]][0] += realised.get(key, 0)
        by_region[key[0]][1] += kl
    print("Quota attainment by regional, whole period: " + ", ".join(f"{k} {pct(*v)}" for k, v in sorted(by_region.items(), key=lambda kv: -pct(*kv[1]))))
    oct_bio = [(realised.get(k, 0), kl) for k, kl in given.items() if k[0] == "Sulawesi" and k[1] == "Biosolar" and k[2] == "2026-10-01"]
    print(f"Biosolar Sulawesi, Oct 2026: realised {oct_bio[0][0]:,} of quota {oct_bio[0][1]:,} = {pct(*oct_bio[0])}%")
    pm = [(realised.get(k, 0), kl) for k, kl in given.items() if k[0] == "Papua Maluku" and k[1] == "Pertalite" and k[2].startswith("2026")]
    print(f"Pertalite Papua Maluku, 2026: {pct(sum(a for a, _ in pm), sum(b for _, b in pm))}%")
    spbu = [c for c in customers if c["segmen_bisnis"] == "Ritel_SPBU"]
    types = defaultdict(int)
    for c in spbu:
        types[c["nama_tipe_pelanggan"]] += 1
    print(f"SPBU registered: {len(spbu)} ({dict(types)}); industrial: {len(customers) - len(spbu)}; active SPBU: {len({d['kode_pelanggan'] for d in deliveries if d['segmen_bisnis'] == 'Ritel_SPBU'})}")
    nov = [d for d in deliveries if d["tanggal_transaksi"] >= "2026-11-01"]
    print(f"Deliveries in Nov 2026: {len(nov)} (the data ends 2026-10-31)")


if __name__ == "__main__":
    main()

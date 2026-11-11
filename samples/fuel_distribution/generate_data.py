#!/usr/bin/env python3
"""Generate synthetic downstream fuel distribution data (BBM) in the style of Pertamina Patra Niaga loading orders.

Two tables that share `kode_pelanggan`:
  * customers.csv   one row per SPBU (COCO / CODO / DODO) and per industrial customer, with its home terminal and standard distance
  * deliveries.csv  one row per loading order (LO): terminal to customer, product, volume in KL, price, truck, distance, duration, status

Deterministic (fixed seed): running it again writes identical CSVs. Entirely synthetic, no real station or company data.
Planted patterns, so test answers are checkable (the script prints how each one came out):
  * Late deliveries are far more common in Papua Maluku and Kalimantan, and at DODO (dealer operated) stations than at COCO.
  * Demand peaks in March (Ramadan) and December, with more late deliveries in those months.
  * The Kertapati terminal is down in August 2025: its customers are served from Panjang, 1.8x farther, and arrive late.
  * Subsidised fuel (Pertalite, Biosolar) is most of the retail volume; the price of non-subsidised fuel moves a little every month.
  * Mining buys the most diesel; aviation fuel (Avtur) goes only to airports.
A loading order never carries more than its truck holds, and "Terlambat" means the duration went over the SLA.

Usage: python samples/fuel_distribution/generate_data.py [--rows 200000]
"""
from __future__ import annotations

import argparse
import bisect
import csv
import random
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

OUT = Path(__file__).resolve().parent / "data"
SEED = 2026
ROWS = 200_000
SPBU_COUNT, INDUSTRY_COUNT = 3000, 400
START, END = date(2025, 1, 1), date(2026, 10, 31)

REGIONALS = {  # name -> (code, terminals, share of customers, distance scale)
    "Sumbagut": ("1", ["Medan Group", "Siantar", "Kisaran"], 12, 1.0),
    "Sumbagsel": ("2", ["Kertapati", "Panjang", "Jambi"], 9, 1.0),
    "Jawa Bagian Barat": ("3", ["Plumpang", "Tanjung Gerem", "Balongan"], 22, 0.6),
    "Jawa Bagian Tengah": ("4", ["Rewulu", "Pengapon", "Maos"], 17, 0.7),
    "Jatimbalinus": ("5", ["Surabaya Group", "Tuban", "Manggis"], 18, 0.8),
    "Kalimantan": ("6", ["Tanjung Batu", "Pontianak", "Banjarmasin"], 8, 1.7),
    "Sulawesi": ("7", ["Makassar", "Bitung", "Donggala"], 9, 1.4),
    "Papua Maluku": ("8", ["Wayame", "Jayapura", "Sorong"], 5, 2.0),
}
PLATE_PREFIX = {"Sumbagut": "BK", "Sumbagsel": "BG", "Jawa Bagian Barat": "B", "Jawa Bagian Tengah": "H", "Jatimbalinus": "L",
                "Kalimantan": "KT", "Sulawesi": "DD", "Papua Maluku": "PA"}
JAVA = {"Jawa Bagian Barat", "Jawa Bagian Tengah", "Jatimbalinus"}
REGION_DELAY = {"Sumbagut": 1.2, "Sumbagsel": 1.0, "Jawa Bagian Barat": 1.0, "Jawa Bagian Tengah": 0.9, "Jatimbalinus": 0.9,
                "Kalimantan": 2.2, "Sulawesi": 1.4, "Papua Maluku": 2.6}
TYPE_DELAY = {"COCO": 0.7, "CODO": 1.1, "DODO": 1.5, "Industri": 0.8}
SPBU_TYPES = {"COCO": ("1", 10), "CODO": ("3", 15), "DODO": ("4", 75)}

PRODUCTS = {  # name -> (category, base price IDR per liter)
    "Pertalite": ("Subsidi", 10000), "Biosolar": ("Subsidi", 6800), "Pertamax": ("Non-Subsidi", 12950),
    "Pertamax Turbo": ("Non-Subsidi", 14400), "Dexlite": ("Non-Subsidi", 14550), "Pertamina Dex": ("Non-Subsidi", 15100),
    "Solar Industri (HSD)": ("Non-Subsidi", 16200), "MFO 180 cSt": ("Non-Subsidi", 13800),
    "Pertamax Industri": ("Non-Subsidi", 15500), "Avtur": ("Non-Subsidi", 17100),
}
RETAIL_MIX = {"Pertalite": 40, "Biosolar": 25, "Pertamax": 20, "Dexlite": 8, "Pertamax Turbo": 4, "Pertamina Dex": 3}
SECTORS = {  # sector -> (share of industrial customers, product mix)
    "Pertambangan": (25, {"Solar Industri (HSD)": 80, "MFO 180 cSt": 20}),
    "Kelautan_Perkapalan": (15, {"MFO 180 cSt": 60, "Solar Industri (HSD)": 40}),
    "Konstruksi": (15, {"Solar Industri (HSD)": 85, "Pertamax Industri": 15}),
    "Manufaktur": (20, {"MFO 180 cSt": 45, "Solar Industri (HSD)": 35, "Pertamax Industri": 20}),
    "Pembangkit_Listrik": (10, {"MFO 180 cSt": 55, "Solar Industri (HSD)": 45}),
    "Penerbangan": (15, {"Avtur": 100}),
}
TRUCK_CAPACITY = {16: 20, 24: 35, 32: 30, 40: 15}
MONTH_DEMAND = {3: 1.3, 12: 1.35, 1: 0.95, 2: 0.95}
PEAK_MONTHS = (3, 12)

DELIVERY_COLUMNS = [
    "id_lo", "tanggal_transaksi", "segmen_bisnis", "regional", "fuel_terminal", "kode_pelanggan", "nama_tipe_pelanggan", "produk",
    "kategori_bbm", "volume_kl", "harga_per_liter_idr", "total_nilai_idr", "nopol_mobil_tangki", "kapasitas_tangki_kl",
    "jarak_tempuh_km", "durasi_kirim_menit", "sla_menit", "status_pengiriman",
]


def month_index(d: date) -> int:
    return (d.year - START.year) * 12 + d.month - START.month


def build_calendar() -> list[float]:
    cumulative, total = [], 0.0
    for i in range((END - START).days + 1):
        d = START + timedelta(days=i)
        total += MONTH_DEMAND.get(d.month, 1.0) * (1 + 0.01 * month_index(d))
        cumulative.append(total)
    return cumulative


def build_customers(rng: random.Random) -> list[dict]:
    names = list(REGIONALS)
    weights = [REGIONALS[r][2] for r in names]
    used: set[str] = set()
    customers: list[dict] = []
    for _ in range(SPBU_COUNT):
        region = rng.choices(names, weights=weights)[0]
        code, terminals, _, scale = REGIONALS[region]
        kind = rng.choices(list(SPBU_TYPES), weights=[w for _, w in SPBU_TYPES.values()])[0]
        while True:
            kode = f"{code}{SPBU_TYPES[kind][0]}.{rng.randint(100, 999)}.{rng.randint(1, 50):02d}"
            if kode not in used:
                used.add(kode)
                break
        mix = dict(RETAIL_MIX)
        if kind == "DODO" and region not in JAVA:  # small dealer stations outside Java do not sell the premium grades
            mix.pop("Pertamax Turbo")
            mix.pop("Pertamina Dex")
        customers.append({
            "kode": kode, "segmen": "Ritel_SPBU", "tipe_nama": f"SPBU_{kind}", "kind": kind, "region": region,
            "terminal": rng.choice(terminals), "distance": round(min(400.0, rng.uniform(8, 160) * scale), 1),
            "weight": rng.lognormvariate(0, 0.6), "products": list(mix), "pw": list(mix.values()),
        })
    sectors = list(SECTORS)
    for _ in range(INDUSTRY_COUNT):
        region = rng.choices(names, weights=weights)[0]
        code, terminals, _, scale = REGIONALS[region]
        sector = rng.choices(sectors, weights=[SECTORS[s][0] for s in sectors])[0]
        while True:
            kode = f"IND-{code}{rng.randint(10000, 99999)}"
            if kode not in used:
                used.add(kode)
                break
        mix = SECTORS[sector][1]
        customers.append({
            "kode": kode, "segmen": "Industri_B2B", "tipe_nama": f"Industri_{sector}", "kind": "Industri", "region": region,
            "terminal": rng.choice(terminals), "distance": round(min(400.0, rng.uniform(8, 160) * scale), 1),
            "weight": rng.lognormvariate(0, 0.5), "products": list(mix), "pw": list(mix.values()),
        })
    return customers


def build_prices(rng: random.Random) -> dict[str, list[int]]:
    months = month_index(END) + 1
    prices: dict[str, list[int]] = {}
    for name, (category, base) in PRODUCTS.items():
        if category == "Subsidi":
            prices[name] = [base] * months
            continue
        drift, series = 0.0, []
        for _ in range(months):
            drift = max(-0.08, min(0.08, drift + rng.gauss(0, 0.012)))
            series.append(int(round(base * (1 + drift) / 50) * 50))
        prices[name] = series
    return prices


def build_trucks(rng: random.Random) -> dict[str, list[dict]]:
    trucks: dict[str, list[dict]] = {}
    for region, (_, terminals, _, _) in REGIONALS.items():
        for terminal in terminals:
            fleet = []
            for _ in range(40):
                plate = f"{PLATE_PREFIX[region]} {rng.randint(1000, 9999)} {rng.choice(['PTN', 'SFU', 'BBM', 'PNL'])}"
                fleet.append({"plate": plate, "capacity": rng.choices(list(TRUCK_CAPACITY), weights=list(TRUCK_CAPACITY.values()))[0]})
            trucks[terminal] = fleet
    return trucks


def generate(rows: int = ROWS, out: Path = OUT) -> dict:
    rng = random.Random(SEED)
    out.mkdir(parents=True, exist_ok=True)
    customers = build_customers(rng)
    prices = build_prices(rng)
    trucks = build_trucks(rng)
    calendar = build_calendar()
    pools = {}
    for segment in ("Ritel_SPBU", "Industri_B2B"):
        members = [c for c in customers if c["segmen"] == segment]
        total, cumulative = 0.0, []
        for c in members:
            total += c["weight"]
            cumulative.append(total)
        pools[segment] = (members, cumulative)

    deliveries: list[dict] = []
    for _ in range(rows):
        x = rng.random() * calendar[-1]
        day = START + timedelta(days=min(bisect.bisect_left(calendar, x), len(calendar) - 1))
        segment = "Ritel_SPBU" if rng.random() < 0.75 else "Industri_B2B"
        members, cumulative = pools[segment]
        c = rng.choices(members, cum_weights=cumulative)[0]
        served_from, detour = c["terminal"], 1.0
        if day.year == 2025 and day.month == 8 and c["terminal"] == "Kertapati" and rng.random() < 0.7:
            served_from, detour = "Panjang", 1.8  # Kertapati is down: served from Panjang, farther away
        product = rng.choices(c["products"], weights=c["pw"])[0]
        category = PRODUCTS[product][0]
        fleet = trucks[served_from] if segment == "Industri_B2B" else [t for t in trucks[served_from] if t["capacity"] <= 32]
        truck = rng.choice(fleet)
        capacity = truck["capacity"]
        volume = capacity if (segment == "Ritel_SPBU" or rng.random() < 0.85) else rng.choice([v for v in (8, 16) if v <= capacity])
        price = prices[product][month_index(day)]
        distance = round(c["distance"] * rng.uniform(0.95, 1.05) * detour, 1)
        sla = round(c["distance"] / 40 * 60 + 60)  # contracted on the standard distance
        duration = distance / rng.uniform(35, 55) * 60 + rng.randint(15, 45)
        p_delay = 0.10 * REGION_DELAY[c["region"]] * TYPE_DELAY[c["kind"]] * (1.3 if day.month in PEAK_MONTHS else 1.0)
        if detour > 1:
            p_delay += 0.3
        if rng.random() < p_delay:
            duration += rng.uniform(60, 300)
        duration = int(duration)
        in_transit = day == END
        deliveries.append({
            "tanggal_transaksi": day, "segmen_bisnis": segment, "regional": c["region"], "fuel_terminal": served_from,
            "kode_pelanggan": c["kode"], "nama_tipe_pelanggan": c["tipe_nama"], "produk": product, "kategori_bbm": category,
            "volume_kl": volume, "harga_per_liter_idr": price, "total_nilai_idr": volume * 1000 * price,
            "nopol_mobil_tangki": truck["plate"], "kapasitas_tangki_kl": capacity, "jarak_tempuh_km": distance,
            "durasi_kirim_menit": "" if in_transit else duration, "sla_menit": sla,
            "status_pengiriman": "Dalam_Perjalanan" if in_transit else ("Terlambat" if duration > sla else "Terkirim"),
        })
    deliveries.sort(key=lambda r: (r["tanggal_transaksi"], r["kode_pelanggan"]))
    for n, row in enumerate(deliveries, start=1):
        row["id_lo"] = f"LO-{row['tanggal_transaksi'].year}{n:07d}"
    with (out / "deliveries.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=DELIVERY_COLUMNS)
        writer.writeheader()
        writer.writerows(deliveries)
    with (out / "customers.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["kode_pelanggan", "segmen_bisnis", "nama_tipe_pelanggan", "regional", "fuel_terminal", "jarak_standar_km"])
        for c in customers:
            writer.writerow([c["kode"], c["segmen"], c["tipe_nama"], c["region"], c["terminal"], c["distance"]])
    print(f"customers.csv: {len(customers)} rows\ndeliveries.csv: {len(deliveries)} rows")
    return {"customers": customers, "deliveries": deliveries}


def pct(a: float, b: float) -> str:
    return f"{a * 100 / b:.1f}%" if b else "n/a"


def report(deliveries: list[dict]) -> None:
    done = [r for r in deliveries if r["status_pengiriman"] != "Dalam_Perjalanan"]

    def late(rows) -> str:
        return pct(sum(r["status_pengiriman"] == "Terlambat" for r in rows), len(rows))

    print("\nPlanted patterns, as they came out:")
    volume = sum(r["volume_kl"] for r in deliveries)
    print(f"  {len(deliveries):,} loading orders, {volume:,} KL, IDR {sum(r['total_nilai_idr'] for r in deliveries) / 1e12:.2f} trillion; late overall {late(done)}")
    by_region = defaultdict(list)
    for r in done:
        by_region[r["regional"]].append(r)
    print("  late rate by regional " + ", ".join(f"{k} {late(v)}" for k, v in sorted(by_region.items(), key=lambda kv: -sum(x["status_pengiriman"] == "Terlambat" for x in kv[1]) / len(kv[1]))))
    by_type = defaultdict(list)
    for r in done:
        if r["segmen_bisnis"] == "Ritel_SPBU":
            by_type[r["nama_tipe_pelanggan"]].append(r)
    print("  late rate by station type " + ", ".join(f"{k} {late(v)}" for k, v in sorted(by_type.items())))
    retail = [r for r in deliveries if r["segmen_bisnis"] == "Ritel_SPBU"]
    subsidi = sum(r["volume_kl"] for r in retail if r["kategori_bbm"] == "Subsidi")
    print(f"  subsidised share of retail volume {pct(subsidi, sum(r['volume_kl'] for r in retail))}")
    per_product = Counter()
    for r in deliveries:
        per_product[r["produk"]] += r["volume_kl"]
    print("  volume by product (KL) " + ", ".join(f"{k} {v:,}" for k, v in per_product.most_common()))
    month = Counter(r["tanggal_transaksi"].strftime("%y-%m") for r in deliveries)
    print("  orders per month " + ", ".join(f"{m}:{month[m]}" for m in sorted(month)))
    kert = Counter()
    for r in deliveries:
        if r["fuel_terminal"] in ("Kertapati", "Panjang") and r["tanggal_transaksi"].year == 2025 and r["tanggal_transaksi"].month in (7, 8, 9):
            kert[(r["fuel_terminal"], r["tanggal_transaksi"].month)] += 1
    print("  Kertapati / Panjang orders Jul-Sep 2025 " + ", ".join(f"{t} m{m}:{n}" for (t, m), n in sorted(kert.items())))
    over = sum(1 for r in deliveries if r["volume_kl"] > r["kapasitas_tangki_kl"])
    print(f"  orders above the truck capacity: {over}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--rows", type=int, default=ROWS)
    args = parser.parse_args(argv)
    report(generate(args.rows)["deliveries"])


if __name__ == "__main__":
    main()

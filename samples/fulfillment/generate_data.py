#!/usr/bin/env python3
"""Generate the synthetic fulfillment and delivery data (two tables that share `order_id` and `region_name`).

Deterministic (fixed seed): running it again writes identical CSVs. Planted patterns, so test answers are checkable:
  * Kalimantan x NusaCargo is late far more often than the rest (carrier review territory).
  * Sumatera x KilatKirim is late far more often from June to August.
  * Home & Living (bulky goods) is late more often; Jawa Timur is mildly worse than average; Electronics fails delivery more; Fashion is returned more.
  * Marketplace orders take longer to fulfil.

Usage: python samples/fulfillment/generate_data.py
"""
from __future__ import annotations

import csv
import random
from datetime import date, timedelta
from pathlib import Path

OUT = Path(__file__).resolve().parent / "data"
SEED = 42
ORDERS = 8000
START, END = date(2026, 1, 1), date(2026, 8, 31)

REGIONS = {  # region -> (warehouse, weight)
    "Jabodetabek": ("WH-Jakarta", 24), "Jawa Barat": ("WH-Jakarta", 16), "Jawa Tengah": ("WH-Surabaya", 12),
    "Jawa Timur": ("WH-Surabaya", 14), "Sumatera": ("WH-Medan", 14), "Kalimantan": ("WH-Surabaya", 8),
    "Sulawesi": ("WH-Surabaya", 7), "Bali-Nusa Tenggara": ("WH-Surabaya", 5),
}
CHANNELS = {"Website": 30, "Mobile App": 45, "Marketplace": 25}
CATEGORIES = {"Electronics": 22, "Fashion": 30, "Home & Living": 18, "Beauty": 15, "Grocery": 15}
CARRIERS = ("FastExpress", "KilatKirim", "NusaCargo")
SLA = {"Regular": 4, "Express": 2}


def pick(rng: random.Random, weights: dict):
    return rng.choices(list(weights), weights=list(weights.values()))[0]


def carrier_for(rng: random.Random, region: str) -> str:
    weights = {"FastExpress": 40, "KilatKirim": 35, "NusaCargo": 25}
    if region == "Kalimantan":
        weights = {"FastExpress": 20, "KilatKirim": 20, "NusaCargo": 60}
    return pick(rng, weights)


def late_probability(region: str, carrier: str, service: str, month: int, category: str) -> float:
    p = 0.07
    if region == "Jawa Timur":
        p = 0.13
    if region == "Kalimantan" and carrier == "NusaCargo":
        p = 0.30
    if region == "Sumatera" and carrier == "KilatKirim" and month in (6, 7, 8):
        p = 0.28
    if category == "Home & Living":  # bulky goods
        p += 0.05
    if service == "Express":
        p += 0.03
    return p


def main() -> None:
    rng = random.Random(SEED)
    OUT.mkdir(parents=True, exist_ok=True)
    span = (END - START).days
    orders, shipments = [], []
    for n in range(1, ORDERS + 1):
        order_id = f"ORD-{n:06d}"
        order_date = START + timedelta(days=rng.randint(0, span))
        region = pick(rng, {r: w for r, (_, w) in REGIONS.items()})
        warehouse = REGIONS[region][0]
        channel, category = pick(rng, CHANNELS), pick(rng, CATEGORIES)
        base_value = {"Electronics": 2_400_000, "Fashion": 450_000, "Home & Living": 900_000, "Beauty": 300_000, "Grocery": 250_000}[category]
        order_value = int(base_value * rng.uniform(0.4, 2.2) // 1000 * 1000)
        items = rng.randint(1, 5)
        fulfillment_hours = round(max(2.0, rng.gauss(14 + (6 if channel == "Marketplace" else 0), 4)), 1)
        status = "Delivered"
        if rng.random() < 0.04:
            status = "Cancelled"
        orders.append({
            "order_id": order_id, "order_date": order_date.isoformat(), "region_name": region, "warehouse": warehouse,
            "channel": channel, "product_category": category, "items": items, "order_value": order_value,
            "fulfillment_hours": fulfillment_hours, "order_status": status,
        })
        if status == "Cancelled":
            continue
        carrier = carrier_for(rng, region)
        service = "Express" if rng.random() < 0.28 else "Regular"
        sla = SLA[service]
        ship_date = order_date + timedelta(days=1 if fulfillment_hours <= 24 else 2)
        if rng.random() < late_probability(region, carrier, service, order_date.month, category):
            days = sla + rng.randint(1, 3)
        else:
            days = rng.randint(1, sla)
        fail_p = 0.05 if category == "Electronics" else 0.02
        delivery_status = "Failed" if rng.random() < fail_p else "Delivered"
        if delivery_status == "Delivered" and rng.random() < (0.12 if category == "Fashion" else 0.05):
            delivery_status = "Returned"
            orders[-1]["order_status"] = "Returned"
        shipments.append({
            "shipment_id": f"SHP-{len(shipments) + 1:06d}", "order_id": order_id, "region_name": region, "carrier": carrier,
            "service_level": service, "ship_date": ship_date.isoformat(),
            "delivered_date": (ship_date + timedelta(days=days)).isoformat(), "delivery_days": days, "sla_days": sla,
            "is_late": str(days > sla).lower(), "delivery_status": delivery_status,
        })
    for name, rows in (("orders", orders), ("shipments", shipments)):
        with (OUT / f"{name}.csv").open("w", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        print(f"{name}.csv: {len(rows)} rows")


if __name__ == "__main__":
    main()

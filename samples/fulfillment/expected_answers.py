#!/usr/bin/env python3
"""Print the ground truth for the fulfillment test questions, computed straight from the CSVs.

Usage: python samples/fulfillment/expected_answers.py
Compare each line with what Ask Data answers (same numbers, rounded to one decimal).
"""
from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

DATA = Path(__file__).resolve().parent / "data"
orders = list(csv.DictReader((DATA / "orders.csv").open()))
shipments = list(csv.DictReader((DATA / "shipments.csv").open()))
order_of = {o["order_id"]: o for o in orders}
JUN_AUG, MAR_MAY = ("06", "07", "08"), ("03", "04", "05")


def late_rate(rows) -> float:
    return round(100 * sum(r["is_late"] == "true" for r in rows) / len(rows), 1)


def share(rows, field, value) -> float:
    return round(100 * sum(r[field] == value for r in rows) / len(rows), 1)


def by(rows, key) -> dict:
    groups = defaultdict(list)
    for row in rows:
        groups[key(row)].append(row)
    return dict(sorted(groups.items()))


def show(title, mapping) -> None:
    print(f"{title}: " + ", ".join(f"{k}={v}" for k, v in mapping.items()))


def main() -> None:
    print(f"orders={len(orders)} shipments={len(shipments)} total_order_value={sum(int(o['order_value']) for o in orders)}")
    show("orders per month", {k: len(v) for k, v in by(orders, lambda o: o["order_date"][:7]).items()})
    print("cancellation rate %:", share(orders, "order_status", "Cancelled"))
    print("late delivery rate % (all):", late_rate(shipments), "| average delivery days:", round(sum(int(r["delivery_days"]) for r in shipments) / len(shipments), 2))
    print("failed delivery rate %:", share(shipments, "delivery_status", "Failed"), "| return rate %:", share(shipments, "delivery_status", "Returned"))
    show("late rate % by region", {k: late_rate(v) for k, v in by(shipments, lambda r: r["region_name"]).items()})
    show("late rate % by carrier", {k: late_rate(v) for k, v in by(shipments, lambda r: r["carrier"]).items()})
    show("late rate % Mar-May by region", {k: late_rate(v) for k, v in by([r for r in shipments if r["ship_date"][5:7] in MAR_MAY], lambda r: r["region_name"]).items()})
    show("late rate % Jun-Aug by region", {k: late_rate(v) for k, v in by([r for r in shipments if r["ship_date"][5:7] in JUN_AUG], lambda r: r["region_name"]).items()})
    kn = [r for r in shipments if r["region_name"] == "Kalimantan Timur" and r["carrier"] == "NusaCargo"]
    print("late rate % Kalimantan Timur x NusaCargo:", late_rate(kn), f"(n={len(kn)})")
    sk = [r for r in shipments if r["region_name"] == "Sumatera Utara" and r["carrier"] == "KilatKirim"]
    print("late rate % Sumatera Utara x KilatKirim Jun-Aug:", late_rate([r for r in sk if r["ship_date"][5:7] in JUN_AUG]), "| Jan-May:", late_rate([r for r in sk if r["ship_date"][5:7] not in JUN_AUG]))
    show("late rate % by product category (needs the order table: published view)", {k: late_rate(v) for k, v in by(shipments, lambda r: order_of[r["order_id"]]["product_category"]).items()})
    show("late rate % by channel (needs the order table: published view)", {k: late_rate(v) for k, v in by(shipments, lambda r: order_of[r["order_id"]]["channel"]).items()})
    show("average fulfillment hours by channel", {k: round(sum(float(o["fulfillment_hours"]) for o in v) / len(v), 1) for k, v in by(orders, lambda o: o["channel"]).items()})
    show("fulfillment hours by region", {k: round(sum(float(o["fulfillment_hours"]) for o in v) / len(v), 1) for k, v in by(orders, lambda o: o["region_name"]).items()})
    show("failed rate % by category", {k: share(v, "delivery_status", "Failed") for k, v in by(shipments, lambda r: order_of[r["order_id"]]["product_category"]).items()})
    show("return rate % by category", {k: share(v, "delivery_status", "Returned") for k, v in by(shipments, lambda r: order_of[r["order_id"]]["product_category"]).items()})
    pairs = {f"{k[0]} x {k[1]}": late_rate(v) for k, v in by(shipments, lambda r: (r["region_name"], r["carrier"])).items()}
    show("region x carrier pairs above the 15% review threshold", {k: v for k, v in sorted(pairs.items(), key=lambda kv: -kv[1]) if v > 15})
    above = late_rate(shipments)
    regions = {k: late_rate(v) for k, v in by(shipments, lambda r: r["region_name"]).items()}
    print(f"regions above the overall late rate ({above}%):", ", ".join(k for k, v in regions.items() if v > above))


if __name__ == "__main__":
    main()

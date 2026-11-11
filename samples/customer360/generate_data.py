#!/usr/bin/env python3
"""Generate the synthetic Customer 360 data: five tables that share `customer_id`.

Deterministic (fixed seed): running it again writes identical CSVs. No PII: only an id and coarse attributes.
Window: 1 Jan 2025 to 31 Aug 2026. Planted patterns, so test answers are checkable (the script prints how each one came out):
  * Customers with 2-3 Delivery tickets within 60 days churn about 3x as often (45% against 15%).
  * Kalimantan Timur has the most Delivery tickets, the most such customers and the highest churn (same story as the NusaCargo
    pattern in the fulfillment sample).
  * Platinum (top 8% by spend) brings roughly a third of the revenue.
  * WhatsApp converts best, Ads worst.
  * Customers acquired through the Marketplace buy less and with bigger discounts.
  * Transactions peak in March (Ramadan) and in November and December.

Usage: python samples/customer360/generate_data.py
"""
from __future__ import annotations

import bisect
import csv
import math
import random
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

OUT = Path(__file__).resolve().parent / "data"
SEED = 360
CUSTOMERS = 5000
START, END = date(2025, 1, 1), date(2026, 8, 31)

REGIONS = {
    "DKI Jakarta": 24, "Jawa Barat": 16, "Jawa Tengah": 12, "Jawa Timur": 14,
    "Sumatera Utara": 14, "Kalimantan Timur": 8, "Sulawesi Selatan": 7, "Bali": 5,
}
AGE_BANDS = {"18-24": 18, "25-34": 34, "35-44": 27, "45-54": 14, "55+": 7}
GENDERS = {"Female": 52, "Male": 48}
ACQUISITION = {"Organic": 28, "Paid Ads": 24, "Referral": 14, "Marketplace": 18, "Social": 16}
CATEGORIES = {"Electronics": 22, "Fashion": 30, "Home & Living": 18, "Beauty": 15, "Grocery": 15}
BASE_VALUE = {"Electronics": 2_400_000, "Fashion": 450_000, "Home & Living": 900_000, "Beauty": 300_000, "Grocery": 250_000}
PAYMENT = {"E-Wallet": 34, "Bank Transfer": 22, "Virtual Account": 18, "Credit Card": 14, "COD": 12}
TXN_CHANNELS = {"Website": 28, "App": 42, "Marketplace": 10, "Store": 20}
TXN_CHANNELS_MARKETPLACE_BUYER = {"Website": 10, "App": 20, "Marketplace": 60, "Store": 10}
MONTH_WEIGHT = {3: 1.5, 11: 1.4, 12: 1.5}  # Ramadan, 11.11, year end
TICKET_CATEGORIES = {"Delivery": 30, "Payment": 20, "Product": 32, "Account": 18}
TICKET_CATEGORIES_KALTIM = {"Delivery": 55, "Payment": 14, "Product": 20, "Account": 11}
PRIORITIES = {"Low": 35, "Medium": 40, "High": 20, "Urgent": 5}
PRIORITY_HOURS = {"Low": 48, "Medium": 30, "High": 16, "Urgent": 6}
TOUCH_CHANNELS = {"Email": 34, "Push": 26, "WhatsApp": 22, "Ads": 18}
FUNNEL = {  # channel -> (opened | sent, clicked | opened, converted | clicked)
    "WhatsApp": (0.65, 0.30, 0.30), "Push": (0.40, 0.12, 0.22), "Email": (0.30, 0.15, 0.20), "Ads": (0.25, 0.12, 0.20),
}
TOUCH_COST = {"WhatsApp": 350, "Email": 25, "Push": 10, "Ads": 1500}
TIER_TOUCH_RATE = {"Platinum": 1.4, "Gold": 1.2, "Silver": 1.0, "Bronze": 0.8}
SEASONAL_CAMPAIGNS = {"Ramadan Sale", "Harbolnas 11.11", "12.12 Sale"}
THEMES = ("Delivery Speed", "Product Quality", "Price", "Customer Service", "App Experience", "Packaging")

ALL_DAYS = (END - START).days + 1
_cum, _total = [], 0.0
for _i in range(ALL_DAYS):
    _total += MONTH_WEIGHT.get((START + timedelta(days=_i)).month, 1.0)
    _cum.append(_total)
CUM = _cum


def pick(rng: random.Random, weights: dict):
    return rng.choices(list(weights), weights=list(weights.values()))[0]


def poisson(rng: random.Random, lam: float) -> int:
    if lam <= 0:
        return 0
    if lam > 30:
        return max(0, round(rng.gauss(lam, math.sqrt(lam))))
    limit, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= limit:
            return k
        k += 1


def sample_day(rng: random.Random, first: date, last: date) -> date:
    """A day in [first, last], seasonal months weighted up."""
    lo_i, hi_i = (first - START).days, (last - START).days
    base = CUM[lo_i - 1] if lo_i > 0 else 0.0
    x = base + rng.random() * (CUM[hi_i] - base)
    return START + timedelta(days=min(bisect.bisect_left(CUM, x, lo_i, hi_i + 1), hi_i))


def uniform_day(rng: random.Random, first: date, last: date) -> date:
    return first + timedelta(days=rng.randint(0, max(0, (last - first).days)))


def make_customer(rng: random.Random, n: int) -> dict:
    region = pick(rng, REGIONS)
    acquisition = pick(rng, ACQUISITION)
    if rng.random() < 0.55:
        signup = uniform_day(rng, date(2024, 1, 1), date(2024, 12, 31))
    else:
        signup = uniform_day(rng, START, END - timedelta(days=14))
    propensity = min(rng.lognormvariate(0, 0.72), 6.0)
    if acquisition == "Referral":
        propensity *= 1.25
    if acquisition == "Marketplace":
        propensity *= 0.75
    bad = rng.random() < (0.30 if region == "Kalimantan Timur" else 0.08)
    active_start = max(signup, START)
    churned = active_start <= END - timedelta(days=120) and rng.random() < (0.45 if bad else 0.15)
    churn_date = None
    if churned:
        churn_date = uniform_day(rng, active_start + timedelta(days=60), END - timedelta(days=7))
    return {
        "id": f"CUS-{n:05d}", "signup": signup, "region": region, "age": pick(rng, AGE_BANDS), "gender": pick(rng, GENDERS),
        "acq": acquisition, "propensity": propensity, "bad": bad, "churned": churned, "churn_date": churn_date,
        "active_start": active_start, "last_day": (churn_date - timedelta(days=1)) if churn_date else END,
        "spend": 0, "tier": "Bronze", "last_txn": active_start,
    }


def months_active(c: dict) -> float:
    return max(0.2, (c["last_day"] - c["active_start"]).days / 30.4)


def make_transactions(rng: random.Random, c: dict, out: list) -> None:
    count = max(1, poisson(rng, 0.40 * c["propensity"] * months_active(c)))
    days: list[date] = []
    if c["signup"] >= START:
        days.append(min(c["signup"] + timedelta(days=rng.randint(0, 7)), c["last_day"]))
        count -= 1
    days += [sample_day(rng, c["active_start"], c["last_day"]) for _ in range(count)]
    c["last_txn"] = max(days)
    weights = TXN_CHANNELS_MARKETPLACE_BUYER if c["acq"] == "Marketplace" else TXN_CHANNELS
    for d in days:
        category = pick(rng, CATEGORIES)
        channel = pick(rng, weights)
        gross = int(BASE_VALUE[category] * rng.uniform(0.4, 2.2) * c["propensity"] ** 0.35 // 1000 * 1000)
        if channel == "Marketplace":
            pct = rng.uniform(0.10, 0.25)
        else:
            pct = rng.uniform(0.02, 0.10) if rng.random() < 0.5 else 0.0
        discount = int(gross * pct // 1000 * 1000)
        c["spend"] += gross - discount
        out.append({
            "customer_id": c["id"], "txn_date": d, "product_category": category, "channel": channel,
            "amount": gross - discount, "discount_amount": discount, "payment_method": pick(rng, PAYMENT),
        })


def ticket_row(rng: random.Random, c: dict, opened: date, category: str, slow: float = 1.0, unhappy: float = 0.0) -> dict:
    priority = pick(rng, PRIORITIES)
    hours = PRIORITY_HOURS[priority] * rng.lognormvariate(0, 0.4) * slow
    if category == "Delivery" and c["region"] == "Kalimantan Timur":
        hours *= 1.6
    status = "Open" if rng.random() < 0.06 else "Resolved"
    csat = ""
    if status == "Resolved" and rng.random() < 0.7:
        score = 4.3 - min(2.0, hours / 40) - unhappy - (0.4 if category == "Delivery" and c["region"] == "Kalimantan Timur" else 0)
        csat = max(1, min(5, round(rng.gauss(score, 0.8))))
    return {
        "customer_id": c["id"], "opened_date": opened, "category": category, "priority": priority,
        "resolution_hours": round(hours, 1) if status == "Resolved" else "", "status": status, "csat_score": csat,
    }


def make_tickets(rng: random.Random, c: dict, out: list) -> None:
    weights = TICKET_CATEGORIES_KALTIM if c["region"] == "Kalimantan Timur" else TICKET_CATEGORIES
    for _ in range(poisson(rng, 0.07 * months_active(c))):
        out.append(ticket_row(rng, c, uniform_day(rng, c["active_start"], c["last_day"]), pick(rng, weights)))
    if c["bad"]:  # 2-3 Delivery tickets inside 60 days, right before the customer left (or at a random point if they stayed)
        anchor = c["last_day"] if c["churned"] else uniform_day(rng, c["active_start"], END)
        first = max(c["active_start"], anchor - timedelta(days=59))
        for _ in range(rng.choice([2, 2, 3])):
            out.append(ticket_row(rng, c, uniform_day(rng, first, anchor), "Delivery", slow=1.5, unhappy=0.8))


def campaign_for(rng: random.Random, c: dict, d: date) -> str:
    if 0 <= (d - c["signup"]).days <= 14:
        return "Welcome Series"
    if d.month == 3 and rng.random() < 0.6:
        return "Ramadan Sale"
    if d.month == 11 and 5 <= d.day <= 12 and rng.random() < 0.7:
        return "Harbolnas 11.11"
    if d.month == 12 and 8 <= d.day <= 14 and rng.random() < 0.7:
        return "12.12 Sale"
    if d.month in (7, 8) and rng.random() < 0.35:
        return "Back to School"
    if d > c["last_txn"] + timedelta(days=60) and rng.random() < 0.5:
        return "Win-back"
    if d.day >= 25 and rng.random() < 0.4:
        return "Payday Promo"
    return "Loyalty Rewards" if c["tier"] in ("Gold", "Platinum") else "Weekly Deals"


def make_touches(rng: random.Random, c: dict, out: list) -> None:
    for _ in range(poisson(rng, 0.9 * TIER_TOUCH_RATE[c["tier"]] * months_active(c))):
        d = uniform_day(rng, c["active_start"], c["last_day"])
        channel = pick(rng, TOUCH_CHANNELS)
        campaign = campaign_for(rng, c, d)
        opened, clicked, converted = FUNNEL[channel]
        boost = (1.3 if c["tier"] in ("Gold", "Platinum") else 1.0) * (0.8 if c["acq"] == "Marketplace" else 1.0)
        boost *= 1.25 if campaign in SEASONAL_CAMPAIGNS else 1.0
        outcome = "Sent"
        if rng.random() < opened:
            outcome = "Opened"
            if rng.random() < clicked:
                outcome = "Clicked"
                if rng.random() < min(0.9, converted * boost):
                    outcome = "Converted"
        out.append({
            "customer_id": c["id"], "touch_date": d, "campaign": campaign, "channel": channel, "outcome": outcome,
            "cost": round(TOUCH_COST[channel] * rng.uniform(0.8, 1.2)),
        })


def make_surveys(rng: random.Random, c: dict, out: list) -> None:
    answers = 0 if rng.random() < 0.5 else (2 if rng.random() < 0.2 else 1)
    mood = 7.5 + {"Platinum": 1.0, "Gold": 0.5}.get(c["tier"], 0.0) - (2.2 if c["bad"] else 0) - (0.6 if c["region"] == "Kalimantan Timur" else 0)
    mood += -0.8 if c["churned"] else 0
    mood += -0.3 if c["acq"] == "Marketplace" else 0
    for _ in range(answers):
        score = max(0, min(10, round(rng.gauss(mood, 2.2))))
        if score <= 6:
            delivery = 45 if (c["bad"] or c["region"] == "Kalimantan Timur") else 25
            weights = {"Delivery Speed": delivery, "Price": 25, "Product Quality": 20, "Customer Service": 15, "Packaging": 8, "App Experience": 7}
        elif score >= 9:
            weights = {"Product Quality": 35, "Customer Service": 25, "Delivery Speed": 20, "Price": 10, "App Experience": 10}
        else:
            weights = {t: 1 for t in THEMES}
        out.append({"customer_id": c["id"], "survey_date": uniform_day(rng, c["active_start"], c["last_day"]), "nps_score": score, "comment_theme": pick(rng, weights)})


def assign_tiers(customers: list[dict]) -> None:
    ranked = sorted(customers, key=lambda c: -c["spend"])
    n = len(ranked)
    for i, c in enumerate(ranked):
        share = i / n
        c["tier"] = "Platinum" if share < 0.08 else "Gold" if share < 0.23 else "Silver" if share < 0.50 else "Bronze"


def write(name: str, rows: list[dict], id_column: str | None = None, prefix: str = "") -> None:
    if id_column:
        for i, row in enumerate(rows, start=1):
            row[id_column] = f"{prefix}-{i:06d}"
        rows[:] = [{id_column: r[id_column], **{k: v for k, v in r.items() if k != id_column}} for r in rows]
    with (OUT / f"{name}.csv").open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"{name}.csv: {len(rows)} rows")


def pct(a: float, b: float) -> str:
    return f"{a * 100 / b:.1f}%" if b else "n/a"


def report(customers, txns, tickets, touches) -> None:
    print("\nPlanted patterns, as they came out:")
    churn = lambda rows: pct(sum(1 for c in rows if c["churned"]), len(rows))  # noqa: E731
    bad = [c for c in customers if c["bad"]]
    rest = [c for c in customers if not c["bad"]]
    print(f"  churn overall {churn(customers)} | 2-3 Delivery tickets in 60 days {churn(bad)} ({len(bad)} customers) | others {churn(rest)}")
    kal = [c for c in customers if c["region"] == "Kalimantan Timur"]
    other = [c for c in customers if c["region"] != "Kalimantan Timur"]
    print(f"  churn Kalimantan Timur {churn(kal)} | other regions {churn(other)}")
    ranking = sorted(REGIONS, key=lambda r: -sum(c["churned"] for c in customers if c["region"] == r) / sum(1 for c in customers if c["region"] == r))
    print("  churn by region " + ", ".join(f"{r} {churn([c for c in customers if c['region'] == r])}" for r in ranking))
    delivery = lambda rows: pct(sum(1 for t in rows if t["category"] == "Delivery"), len(rows))  # noqa: E731
    by_region = {c["id"]: c["region"] for c in customers}
    print(f"  Delivery share of tickets: Kalimantan Timur {delivery([t for t in tickets if by_region[t['customer_id']] == 'Kalimantan Timur'])}"
          f" | others {delivery([t for t in tickets if by_region[t['customer_id']] != 'Kalimantan Timur'])}")
    revenue = sum(c["spend"] for c in customers)
    tiers = Counter(c["tier"] for c in customers)
    print("  customers per tier " + ", ".join(f"{t} {tiers[t]}" for t in ("Platinum", "Gold", "Silver", "Bronze")))
    print(f"  Platinum revenue share {pct(sum(c['spend'] for c in customers if c['tier'] == 'Platinum'), revenue)}; total revenue IDR {revenue:,}")
    funnel = defaultdict(lambda: [0, 0])
    for t in touches:
        funnel[t["channel"]][0] += 1
        funnel[t["channel"]][1] += t["outcome"] == "Converted"
    print("  conversion by channel " + ", ".join(f"{k} {pct(v[1], v[0])}" for k, v in sorted(funnel.items(), key=lambda kv: -kv[1][1] / kv[1][0])))
    market = [c for c in customers if c["acq"] == "Marketplace"]
    others = [c for c in customers if c["acq"] != "Marketplace"]
    print(f"  average spend per customer: Marketplace-acquired IDR {sum(c['spend'] for c in market) // len(market):,} | others IDR {sum(c['spend'] for c in others) // len(others):,}")
    month = Counter(t["txn_date"].strftime("%Y-%m") for t in txns)
    print("  transactions per month " + ", ".join(f"{m[2:]}:{month[m]}" for m in sorted(month)))


def main() -> None:
    rng = random.Random(SEED)
    OUT.mkdir(parents=True, exist_ok=True)
    customers, txns, tickets, touches, surveys = [], [], [], [], []
    for n in range(1, CUSTOMERS + 1):
        c = make_customer(rng, n)
        customers.append(c)
        make_transactions(rng, c, txns)
        make_tickets(rng, c, tickets)
    assign_tiers(customers)
    for c in customers:
        make_touches(rng, c, touches)
        make_surveys(rng, c, surveys)
    for rows in (txns, tickets, touches, surveys):
        rows.sort(key=lambda r: (next(v for k, v in r.items() if k.endswith("_date")), r["customer_id"]))
    write("customers", [{
        "customer_id": c["id"], "signup_date": c["signup"], "region_name": c["region"], "age_band": c["age"], "gender": c["gender"],
        "acquisition_channel": c["acq"], "loyalty_tier": c["tier"], "is_active": str(not c["churned"]).lower(),
        "churn_date": c["churn_date"] or "",
    } for c in customers])
    write("transactions", txns, "transaction_id", "TXN")
    write("support_tickets", tickets, "ticket_id", "TKT")
    write("campaign_touches", touches, "touch_id", "TCH")
    write("nps_surveys", surveys, "survey_id", "SRV")
    report(customers, txns, tickets, touches)


if __name__ == "__main__":
    main()

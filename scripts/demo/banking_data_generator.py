"""Deterministic synthetic banking demo data (Indonesia retail banking)."""
from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Iterable

SCHEMA = "banking_demo"
CUSTOMER_TARGET = 250
TRANSACTION_TARGET = 1000
DATE_START = date(2026, 1, 1)
DATE_END = date(2026, 9, 30)

SEGMENTS = ("Retail", "Priority", "SME")
STATUSES = ("Active", "Dormant", "Closed")
RISK_TIERS = ("Low", "Medium", "High")
CITIES = ("Jakarta", "Bandung", "Surabaya", "Medan", "Makassar", "Yogyakarta")

TX_TYPES = ("Transfer", "Payment", "Purchase", "Withdrawal", "Deposit")
CHANNELS = ("Mobile Banking", "Internet Banking", "ATM", "Branch", "EDC")
MERCHANT_CATS = ("Groceries", "Dining", "Travel", "Utilities", "Healthcare", "Education", "Retail")
TX_STATUSES = ("Success", "Failed", "Pending")

FIRST = (
    "Ayu",
    "Budi",
    "Citra",
    "Dimas",
    "Eka",
    "Fajar",
    "Gita",
    "Hendra",
    "Indah",
    "Joko",
    "Kartika",
    "Lestari",
    "Made",
    "Nadia",
    "Oki",
    "Putri",
    "Rizky",
    "Siti",
    "Taufik",
    "Umar",
    "Vina",
    "Wulan",
    "Yusuf",
    "Zahra",
)
LAST = (
    "Pratama",
    "Santoso",
    "Wijaya",
    "Kusuma",
    "Halim",
    "Nugroho",
    "Saputra",
    "Hidayat",
    "Mahendra",
    "Permata",
    "Anggraini",
    "Setiawan",
    "Utami",
    "Rahman",
    "Susanto",
    "Lestari",
    "Purnama",
    "Gunawan",
    "Siregar",
    "Nasution",
)


@dataclass(frozen=True)
class CustomerRow:
    customer_id: int
    customer_name: str
    segment: str
    city: str
    join_date: date
    customer_status: str
    risk_tier: str


@dataclass(frozen=True)
class TransactionRow:
    transaction_id: int
    customer_id: int
    transaction_date: date
    transaction_type: str
    channel: str
    merchant_category: str
    amount: Decimal
    status: str


def _daterange_days(start: date, end: date) -> int:
    return (end - start).days + 1


def generate_customers(*, seed: int = 42, count: int = CUSTOMER_TARGET) -> list[CustomerRow]:
    rng = random.Random(seed)
    rows: list[CustomerRow] = []
    for cid in range(1, count + 1):
        name = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
        segment = SEGMENTS[cid % len(SEGMENTS)]
        city = CITIES[(cid * 3) % len(CITIES)]
        join_offset = rng.randint(0, 400)
        join_date = DATE_START - timedelta(days=join_offset)
        if cid % 17 == 0:
            status = "Closed"
        elif cid % 11 == 0:
            status = "Dormant"
        else:
            status = "Active"
        risk = RISK_TIERS[(cid + rng.randint(0, 2)) % len(RISK_TIERS)]
        rows.append(
            CustomerRow(
                customer_id=cid,
                customer_name=name,
                segment=segment,
                city=city,
                join_date=join_date,
                customer_status=status,
                risk_tier=risk,
            )
        )
    return rows


def generate_transactions(
    customers: Iterable[CustomerRow],
    *,
    seed: int = 42,
    count: int = TRANSACTION_TARGET,
) -> list[TransactionRow]:
    rng = random.Random(seed + 1)
    cust_ids = [c.customer_id for c in customers]
    active_ids = [c.customer_id for c in customers if c.customer_status == "Active"]
    if not active_ids:
        active_ids = cust_ids
    span = _daterange_days(DATE_START, DATE_END)
    rows: list[TransactionRow] = []
    for tid in range(1, count + 1):
        customer_id = rng.choice(active_ids if tid % 5 else cust_ids)
        day_offset = rng.randint(0, span - 1)
        tx_date = DATE_START + timedelta(days=day_offset)
        tx_type = TX_TYPES[tid % len(TX_TYPES)]
        channel = CHANNELS[(tid + customer_id) % len(CHANNELS)]
        merchant = MERCHANT_CATS[(tid * 7 + customer_id) % len(MERCHANT_CATS)]
        base = rng.randint(15_000, 8_500_000)
        if tx_type == "Withdrawal":
            base = rng.randint(100_000, 3_000_000)
        amount = Decimal(base)
        if tid % 23 == 0:
            status = "Pending"
        elif tid % 19 == 0 or (channel == "ATM" and tid % 13 == 0):
            status = "Failed"
        else:
            status = "Success"
        rows.append(
            TransactionRow(
                transaction_id=tid,
                customer_id=customer_id,
                transaction_date=tx_date,
                transaction_type=tx_type,
                channel=channel,
                merchant_category=merchant,
                amount=amount,
                status=status,
            )
        )
    return rows

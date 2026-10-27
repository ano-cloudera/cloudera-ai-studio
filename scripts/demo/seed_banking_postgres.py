#!/usr/bin/env python3
"""Seed Golden Path banking demo tables into PostgreSQL (schema banking_demo).

Default: dry-run. Use --apply to write. Use --reset to drop and recreate schema data.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import psycopg
from psycopg import sql

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "demo"))

from banking_data_generator import (  # noqa: E402
    CUSTOMER_TARGET,
    DATE_END,
    DATE_START,
    SCHEMA,
    TRANSACTION_TARGET,
    generate_customers,
    generate_transactions,
)

DEFAULT_ADMIN_URL = os.environ.get(
    "BANKING_DEMO_ADMIN_URL",
    "postgresql://m1:m1pass@127.0.0.1:55432/postgres",
)
DEFAULT_APP_URL = os.environ.get(
    "BANKING_DEMO_URL",
    "postgresql://m1:m1pass@127.0.0.1:55432/banking_demo",
)


def _ensure_database(admin_url: str, db_name: str) -> None:
    with psycopg.connect(admin_url) as conn:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (db_name,))
            if cur.fetchone():
                return
            cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(db_name)))


def _ddl(conn: psycopg.Connection, *, reset: bool) -> None:
    with conn.cursor() as cur:
        cur.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(SCHEMA)))
        if reset:
            cur.execute(sql.SQL("DROP TABLE IF EXISTS {}.transactions CASCADE").format(sql.Identifier(SCHEMA)))
            cur.execute(sql.SQL("DROP TABLE IF EXISTS {}.customers CASCADE").format(sql.Identifier(SCHEMA)))
        cur.execute(
            sql.SQL(
                """
                CREATE TABLE IF NOT EXISTS {schema}.customers (
                    customer_id INTEGER PRIMARY KEY,
                    customer_name TEXT NOT NULL,
                    segment TEXT NOT NULL,
                    city TEXT NOT NULL,
                    join_date DATE NOT NULL,
                    customer_status TEXT NOT NULL,
                    risk_tier TEXT NOT NULL
                )
                """
            ).format(schema=sql.Identifier(SCHEMA))
        )
        cur.execute(
            sql.SQL(
                """
                CREATE TABLE IF NOT EXISTS {schema}.transactions (
                    transaction_id INTEGER PRIMARY KEY,
                    customer_id INTEGER NOT NULL REFERENCES {schema}.customers(customer_id),
                    transaction_date DATE NOT NULL,
                    transaction_type TEXT NOT NULL,
                    channel TEXT NOT NULL,
                    merchant_category TEXT NOT NULL,
                    amount NUMERIC(18,2) NOT NULL CHECK (amount > 0),
                    status TEXT NOT NULL
                )
                """
            ).format(schema=sql.Identifier(SCHEMA))
        )


def _insert(conn: psycopg.Connection, *, seed: int) -> dict:
    customers = generate_customers(seed=seed)
    transactions = generate_transactions(customers, seed=seed)
    with conn.cursor() as cur:
        cur.execute(sql.SQL("SELECT COUNT(*) FROM {}.customers").format(sql.Identifier(SCHEMA)))
        existing = int(cur.fetchone()[0])
        if existing > 0:
            return {"skipped": True, "existing_customers": existing}
        cur.executemany(
            sql.SQL(
                """
                INSERT INTO {schema}.customers
                (customer_id, customer_name, segment, city, join_date, customer_status, risk_tier)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """
            ).format(schema=sql.Identifier(SCHEMA)),
            [
                (
                    r.customer_id,
                    r.customer_name,
                    r.segment,
                    r.city,
                    r.join_date,
                    r.customer_status,
                    r.risk_tier,
                )
                for r in customers
            ],
        )
        cur.executemany(
            sql.SQL(
                """
                INSERT INTO {schema}.transactions
                (transaction_id, customer_id, transaction_date, transaction_type, channel, merchant_category, amount, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """
            ).format(schema=sql.Identifier(SCHEMA)),
            [
                (
                    r.transaction_id,
                    r.customer_id,
                    r.transaction_date,
                    r.transaction_type,
                    r.channel,
                    r.merchant_category,
                    r.amount,
                    r.status,
                )
                for r in transactions
            ],
        )
    return {"skipped": False, "customers": len(customers), "transactions": len(transactions)}


def validate(conn: psycopg.Connection) -> dict:
    with conn.cursor() as cur:
        cur.execute(sql.SQL("SELECT COUNT(*) FROM {}.customers").format(sql.Identifier(SCHEMA)))
        cust_n = int(cur.fetchone()[0])
        cur.execute(sql.SQL("SELECT COUNT(*) FROM {}.transactions").format(sql.Identifier(SCHEMA)))
        tx_n = int(cur.fetchone()[0])
        cur.execute(
            sql.SQL(
                """
                SELECT COUNT(*) FROM {schema}.transactions t
                LEFT JOIN {schema}.customers c ON c.customer_id = t.customer_id
                WHERE c.customer_id IS NULL
                """
            ).format(schema=sql.Identifier(SCHEMA))
        )
        orphans = int(cur.fetchone()[0])
        cur.execute(
            sql.SQL("SELECT MIN(transaction_date), MAX(transaction_date) FROM {}.transactions").format(
                sql.Identifier(SCHEMA)
            )
        )
        min_d, max_d = cur.fetchone()
    return {
        "customers": cust_n,
        "transactions": tx_n,
        "orphan_transactions": orphans,
        "transaction_date_min": str(min_d) if min_d else None,
        "transaction_date_max": str(max_d) if max_d else None,
        "distributions": {
            "status": _counter(conn, f"SELECT status, COUNT(*) FROM {SCHEMA}.transactions GROUP BY status"),
            "channel": _counter(conn, f"SELECT channel, COUNT(*) FROM {SCHEMA}.transactions GROUP BY channel"),
            "segment": _counter(conn, f"SELECT segment, COUNT(*) FROM {SCHEMA}.customers GROUP BY segment"),
            "risk_tier": _counter(conn, f"SELECT risk_tier, COUNT(*) FROM {SCHEMA}.customers GROUP BY risk_tier"),
        },
    }


def _counter(conn: psycopg.Connection, query: str) -> dict[str, int]:
    with conn.cursor() as cur:
        cur.execute(query)
        return {str(row[0]): int(row[1]) for row in cur.fetchall()}


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed banking_demo PostgreSQL schema.")
    parser.add_argument("--dry-run", action="store_true", help="Print plan only (default).")
    parser.add_argument("--apply", action="store_true", help="Apply seed to database.")
    parser.add_argument("--reset", action="store_true", help="Drop tables before seed (requires --apply).")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--export-validation", type=Path, help="Write validation JSON evidence.")
    args = parser.parse_args()
    apply = bool(args.apply)
    if args.reset and not apply:
        print("--reset requires --apply", file=sys.stderr)
        return 2

    admin_url = DEFAULT_ADMIN_URL
    app_url = DEFAULT_APP_URL
    db_name = "banking_demo"

    print(f"target_database={db_name} schema={SCHEMA}")
    print(f"admin_url={admin_url.split('@')[-1]}")
    print(f"app_url={app_url.split('@')[-1]}")
    print(f"customers_target={CUSTOMER_TARGET} transactions_target={TRANSACTION_TARGET}")
    print(f"date_range={DATE_START.isoformat()}..{DATE_END.isoformat()} seed={args.seed}")

    if not apply:
        print("DRY-RUN: would ensure database, create schema/tables, insert rows (idempotent skip if populated)")
        if args.reset:
            print("DRY-RUN: --reset would drop banking_demo.customers/transactions")
        return 0

    _ensure_database(admin_url, db_name)
    with psycopg.connect(app_url) as conn:
        conn.autocommit = False
        _ddl(conn, reset=args.reset)
        result = _insert(conn, seed=args.seed)
        conn.commit()
        report = validate(conn)
        report["insert"] = result
        print(json.dumps(report, indent=2))
        if args.export_validation:
            args.export_validation.parent.mkdir(parents=True, exist_ok=True)
            args.export_validation.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
            print(f"Wrote {args.export_validation}")
        if report["orphan_transactions"] != 0:
            print("FK integrity FAILED", file=sys.stderr)
            return 1
        if not (240 <= report["customers"] <= 260 and 950 <= report["transactions"] <= 1050):
            if result.get("skipped"):
                print("Existing seed detected; counts:", report["customers"], report["transactions"])
            else:
                print("Row count out of expected band", file=sys.stderr)
                return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

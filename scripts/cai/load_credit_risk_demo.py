#!/usr/bin/env python3
"""Load the synthetic credit-risk demo CSVs (demo/data) into Trino as Parquet tables.

Usage:
  TRINO_HOST=<host> TRINO_USER=<user> TRINO_PASSWORD=<pw> TRINO_CATALOG=hive TRINO_SCHEMA=default \
    python scripts/cai/load_credit_risk_demo.py [--replace]
Refuses to touch a table that already has rows unless --replace is given (then it drops and recreates it).
"""
from __future__ import annotations

import csv
import os
import sys
from pathlib import Path

import trino

DATA = Path(__file__).resolve().parents[2] / "demo" / "data"
BATCH = 500

TABLES = {
    "credit_applications": [
        ("application_id", "VARCHAR"), ("application_date", "DATE"), ("region_name", "VARCHAR"),
        ("customer_segment", "VARCHAR"), ("application_channel", "VARCHAR"), ("product_category", "VARCHAR"),
        ("credit_score", "INTEGER"), ("dti_ratio", "DOUBLE"), ("requested_amount", "DECIMAL(18,2)"),
        ("decision_status", "VARCHAR"), ("policy_exception_flag", "BOOLEAN"), ("decision_time_hours", "DOUBLE"),
    ],
    "loan_quality": [
        ("loan_id", "VARCHAR"), ("assessment_date", "DATE"), ("region_name", "VARCHAR"),
        ("customer_segment", "VARCHAR"), ("origination_channel", "VARCHAR"), ("product_category", "VARCHAR"),
        ("outstanding_balance", "DECIMAL(18,2)"), ("days_past_due", "INTEGER"), ("delinquency_flag", "BOOLEAN"),
        ("risk_band", "VARCHAR"), ("monthly_installment", "DECIMAL(18,2)"),
    ],
}


def literal(value: str, sql_type: str) -> str:
    if sql_type == "VARCHAR":
        return "'" + value.replace("'", "''") + "'"
    if sql_type == "DATE":
        return f"DATE '{value}'"
    if sql_type == "BOOLEAN":
        return "TRUE" if value.strip().lower() == "true" else "FALSE"
    if sql_type.startswith("DECIMAL"):
        return f"DECIMAL '{value}'"
    return value  # INTEGER / DOUBLE


def main() -> int:
    replace = "--replace" in sys.argv
    catalog, schema = os.environ["TRINO_CATALOG"], os.environ["TRINO_SCHEMA"]
    user = os.environ["TRINO_USER"]
    conn = trino.dbapi.connect(
        host=os.environ["TRINO_HOST"], port=int(os.getenv("TRINO_PORT", "443")), user=user,
        http_scheme=os.getenv("TRINO_HTTP_SCHEME", "https"), catalog=catalog, schema=schema,
        auth=trino.auth.BasicAuthentication(user, os.environ["TRINO_PASSWORD"]),
    )
    cur = conn.cursor()

    def run(sql: str):
        cur.execute(sql)
        return cur.fetchall()

    for table, columns in TABLES.items():
        fq = f'"{catalog}"."{schema}"."{table}"'
        exists = bool(run(f"SHOW TABLES LIKE '{table}'"))
        if exists:
            rows = run(f"SELECT count(*) FROM {fq}")[0][0]
            if rows and not replace:
                print(f"[SKIP] {table} already has {rows} rows (use --replace)")
                continue
            run(f"DROP TABLE {fq}")
        ddl = ", ".join(f"{n} {t}" for n, t in columns)
        run(f"CREATE TABLE {fq} ({ddl}) WITH (format = 'PARQUET')")
        with (DATA / f"{table}.csv").open(newline="") as fh:
            data = list(csv.DictReader(fh))
        for i in range(0, len(data), BATCH):
            values = ",".join(
                "(" + ",".join(literal(r[n], t) for n, t in columns) + ")" for r in data[i : i + BATCH]
            )
            run(f"INSERT INTO {fq} VALUES {values}")
        print(f"[LOAD] {table}: {len(data)} rows, trino count={run(f'SELECT count(*) FROM {fq}')[0][0]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

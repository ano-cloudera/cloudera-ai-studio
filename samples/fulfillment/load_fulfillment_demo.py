#!/usr/bin/env python3
"""Load the synthetic fulfillment data into Trino: two Parquet tables and one governed view that joins them.

Usage (backend venv, from a Session):
  TRINO_HOST=<host> TRINO_USER=<user> TRINO_PASSWORD=<pw> TRINO_CATALOG=hive TRINO_SCHEMA=default \
    python samples/fulfillment/load_fulfillment_demo.py [--replace]
Refuses to touch a table that already has rows unless --replace is given (then it drops and recreates it).
The view is the published join: the data owner creates it, the semantic layer never joins at question time.
"""
from __future__ import annotations

import csv
import os
import sys
from pathlib import Path

import trino

DATA = Path(__file__).resolve().parent / "data"
BATCH = 500

TABLES = {  # table -> (csv file, columns)
    "fulfillment_orders": ("orders.csv", [
        ("order_id", "VARCHAR"), ("order_date", "DATE"), ("region_name", "VARCHAR"), ("warehouse", "VARCHAR"),
        ("channel", "VARCHAR"), ("product_category", "VARCHAR"), ("items", "INTEGER"), ("order_value", "DECIMAL(18,2)"),
        ("fulfillment_hours", "DOUBLE"), ("order_status", "VARCHAR"),
    ]),
    "delivery_shipments": ("shipments.csv", [
        ("shipment_id", "VARCHAR"), ("order_id", "VARCHAR"), ("region_name", "VARCHAR"), ("carrier", "VARCHAR"),
        ("service_level", "VARCHAR"), ("ship_date", "DATE"), ("delivered_date", "DATE"), ("delivery_days", "INTEGER"),
        ("sla_days", "INTEGER"), ("is_late", "BOOLEAN"), ("delivery_status", "VARCHAR"),
    ]),
}

VIEW = """CREATE OR REPLACE VIEW "{catalog}"."{schema}"."v_fulfillment_delivery" AS
SELECT o.order_id, o.order_date, o.region_name, o.warehouse, o.channel, o.product_category, o.order_value,
       o.fulfillment_hours, o.order_status, s.shipment_id, s.carrier, s.service_level, s.ship_date, s.delivered_date,
       s.delivery_days, s.sla_days, s.is_late, s.delivery_status
FROM "{catalog}"."{schema}"."fulfillment_orders" o
JOIN "{catalog}"."{schema}"."delivery_shipments" s ON o.order_id = s.order_id"""


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

    for table, (csv_name, columns) in TABLES.items():
        fq = f'"{catalog}"."{schema}"."{table}"'
        if run(f"SHOW TABLES LIKE '{table}'"):
            rows = run(f"SELECT count(*) FROM {fq}")[0][0]
            if rows and not replace:
                print(f"[SKIP] {table} already has {rows} rows (use --replace)")
                continue
            run(f"DROP TABLE {fq}")
        run(f"CREATE TABLE {fq} (" + ", ".join(f"{n} {t}" for n, t in columns) + ") WITH (format = 'PARQUET')")
        with (DATA / csv_name).open(newline="") as fh:
            data = list(csv.DictReader(fh))
        for i in range(0, len(data), BATCH):
            values = ",".join("(" + ",".join(literal(r[n], t) for n, t in columns) + ")" for r in data[i : i + BATCH])
            run(f"INSERT INTO {fq} VALUES {values}")
        print(f"[LOAD] {table}: {len(data)} rows, trino count={run(f'SELECT count(*) FROM {fq}')[0][0]}")
    run(VIEW.format(catalog=catalog, schema=schema))
    view_count = run(f'SELECT count(*) FROM "{catalog}"."{schema}"."v_fulfillment_delivery"')[0][0]
    print(f"[VIEW] v_fulfillment_delivery: {view_count} rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

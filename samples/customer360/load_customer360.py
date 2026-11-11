#!/usr/bin/env python3
"""Load the synthetic Customer 360 data into Trino: five Parquet tables and one governed view (one row per customer).

Usage (backend venv, from the repo root; the Trino settings come from the environment or from the repo's .env):
  python samples/customer360/load_customer360.py [--replace] [--probe]      # TRINO_CATALOG / TRINO_SCHEMA default to iceberg / default
Use the iceberg catalog: the hive catalog shares its metastore and lists the same names but cannot read an Iceberg table, and a Hive table
with the same name blocks the Iceberg one.
  --probe   only connect and list what is there (reads, writes nothing)
Refuses to touch a table that already has rows unless --replace is given (then it drops and recreates it).
The view is the published one-row-per-customer summary; the semantic layer never joins at question time.
Credentials are never printed.
"""
from __future__ import annotations

import csv
import os
import sys
from pathlib import Path

import trino

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
BATCH = 1000
AS_OF = "2026-08-31"  # the last day of the data; the view measures recency against it so answers stay the same every day

TABLES = {  # table -> (csv file, columns)
    "c360_customers": ("customers.csv", [
        ("customer_id", "VARCHAR"), ("signup_date", "DATE"), ("region_name", "VARCHAR"), ("age_band", "VARCHAR"),
        ("gender", "VARCHAR"), ("acquisition_channel", "VARCHAR"), ("loyalty_tier", "VARCHAR"), ("is_active", "BOOLEAN"),
        ("churn_date", "DATE"),
    ]),
    "c360_transactions": ("transactions.csv", [
        ("transaction_id", "VARCHAR"), ("customer_id", "VARCHAR"), ("txn_date", "DATE"), ("product_category", "VARCHAR"),
        ("channel", "VARCHAR"), ("amount", "DECIMAL(18,2)"), ("discount_amount", "DECIMAL(18,2)"), ("payment_method", "VARCHAR"),
    ]),
    "c360_support_tickets": ("support_tickets.csv", [
        ("ticket_id", "VARCHAR"), ("customer_id", "VARCHAR"), ("opened_date", "DATE"), ("category", "VARCHAR"),
        ("priority", "VARCHAR"), ("resolution_hours", "DOUBLE"), ("status", "VARCHAR"), ("csat_score", "INTEGER"),
    ]),
    "c360_campaign_touches": ("campaign_touches.csv", [
        ("touch_id", "VARCHAR"), ("customer_id", "VARCHAR"), ("touch_date", "DATE"), ("campaign", "VARCHAR"),
        ("channel", "VARCHAR"), ("outcome", "VARCHAR"), ("cost", "DECIMAL(18,2)"),
    ]),
    "c360_nps_surveys": ("nps_surveys.csv", [
        ("survey_id", "VARCHAR"), ("customer_id", "VARCHAR"), ("survey_date", "DATE"), ("nps_score", "INTEGER"),
        ("comment_theme", "VARCHAR"),
    ]),
}

VIEW = """CREATE OR REPLACE VIEW "{catalog}"."{schema}"."v_customer_360" AS
WITH t AS (
  SELECT customer_id, SUM(amount) AS total_spend, SUM(discount_amount) AS total_discount, COUNT(*) AS txn_count, MAX(txn_date) AS last_txn_date
  FROM "{catalog}"."{schema}"."c360_transactions" GROUP BY customer_id
), k AS (
  SELECT customer_id, COUNT(*) AS ticket_count, COUNT(CASE WHEN category = 'Delivery' THEN 1 END) AS delivery_ticket_count, AVG(csat_score) AS avg_csat
  FROM "{catalog}"."{schema}"."c360_support_tickets" GROUP BY customer_id
), m AS (
  SELECT customer_id, COUNT(*) AS touch_count, COUNT(CASE WHEN outcome = 'Converted' THEN 1 END) AS converted_touches
  FROM "{catalog}"."{schema}"."c360_campaign_touches" GROUP BY customer_id
), n AS (
  SELECT customer_id, max_by(nps_score, survey_date) AS last_nps_score
  FROM "{catalog}"."{schema}"."c360_nps_surveys" GROUP BY customer_id
)
SELECT c.customer_id, c.signup_date, c.region_name, c.age_band, c.gender, c.acquisition_channel, c.loyalty_tier, c.is_active, c.churn_date,
       COALESCE(t.total_spend, 0) AS total_spend, COALESCE(t.total_discount, 0) AS total_discount, COALESCE(t.txn_count, 0) AS txn_count,
       t.last_txn_date, date_diff('day', t.last_txn_date, DATE '{as_of}') AS days_since_last_txn,
       COALESCE(k.ticket_count, 0) AS ticket_count, COALESCE(k.delivery_ticket_count, 0) AS delivery_ticket_count, k.avg_csat,
       COALESCE(m.touch_count, 0) AS touch_count, COALESCE(m.converted_touches, 0) AS converted_touches, n.last_nps_score,
       CASE
         WHEN NOT c.is_active THEN 'Churned'
         WHEN c.signup_date >= DATE '2026-07-01' THEN 'New'
         WHEN date_diff('day', t.last_txn_date, DATE '{as_of}') > 180 THEN 'Hibernating'
         WHEN date_diff('day', t.last_txn_date, DATE '{as_of}') > 90 THEN 'At Risk'
         WHEN c.loyalty_tier IN ('Platinum', 'Gold') AND date_diff('day', t.last_txn_date, DATE '{as_of}') <= 45 THEN 'Champions'
         ELSE 'Loyal'
       END AS rfm_segment
FROM "{catalog}"."{schema}"."c360_customers" c
LEFT JOIN t ON c.customer_id = t.customer_id
LEFT JOIN k ON c.customer_id = k.customer_id
LEFT JOIN m ON c.customer_id = m.customer_id
LEFT JOIN n ON c.customer_id = n.customer_id"""


def load_env_file(path: Path) -> None:
    """Fill only the variables that are not already set. Values are never printed."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip().removeprefix("export ").strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def literal(value: str, sql_type: str) -> str:
    if value == "":
        return "NULL"
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
    load_env_file(HERE.parents[1] / ".env")
    replace, probe = "--replace" in sys.argv, "--probe" in sys.argv
    catalog, schema = os.getenv("TRINO_CATALOG", "iceberg"), os.getenv("TRINO_SCHEMA", "default")
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

    print(f"[TARGET] {catalog}.{schema}")
    if probe:
        print("[CATALOGS]", [r[0] for r in run("SHOW CATALOGS")])
        print(f"[TABLES in {catalog}.{schema}]", [r[0] for r in run(f'SHOW TABLES FROM "{catalog}"."{schema}"')])
        return 0

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
        print(f"[LOAD] {table}: {len(data)} csv rows, trino count={run(f'SELECT count(*) FROM {fq}')[0][0]}")
    run(VIEW.format(catalog=catalog, schema=schema, as_of=AS_OF))
    view_count = run(f'SELECT count(*) FROM "{catalog}"."{schema}"."v_customer_360"')[0][0]
    print(f"[VIEW] v_customer_360: {view_count} rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

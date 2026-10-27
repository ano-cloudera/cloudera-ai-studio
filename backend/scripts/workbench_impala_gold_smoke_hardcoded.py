#!/usr/bin/env python3
"""
CAI Workbench → Impala Ingram smoke test (hardcoded, no .env).

Run from repo root on Workbench (Kerberos usually already active):
  python backend/scripts/workbench_impala_gold_smoke_hardcoded.py

Or paste this file into a Workbench session and run. Adjust IMPALA_* below if needed.
"""

from __future__ import annotations

# --- ### IMPALA CREDENTIALS INGRAM ENV (same as repo-root .env block) ---
IMPALA_HOST = "cbase02.imid.local"
IMPALA_PORT = 21050
IMPALA_DATABASE = "gold"
IMPALA_AUTH_MECHANISM = "GSSAPI"
IMPALA_USER = "partner-multipolar"
IMPALA_PASSWORD = "imid@Jakarta1!"
IMPALA_USE_SSL = True
IMPALA_USE_HTTP_TRANSPORT = False
IMPALA_HTTP_PATH = "cliservice"
IMPALA_KERBEROS_SERVICE_NAME = "impala"
QUERY_TIMEOUT_S = 120

# All 24 OSSIE dataset sources (gold.*) — must match tempo_core.ossie.yaml / EXPECTED_SOURCES
GOLD_SOURCES = (
    "gold.rpt_sap_monthly_executive_semantic",
    "gold.rpt_sap_material_month_semantic",
    "gold.rpt_service_level_material_month_semantic",
    "gold.rpt_sap_customer_reconciliation_semantic",
    "gold.rpt_sales_office_performance_semantic",
    "gold.corr_b2b_branch_estore_month",
    "gold.corr_b2b_material_plu",
    "gold.corr_stock_tempo_month_seta",
    "gold.rpt_sat_dc_month",
    "gold.rpt_sat_oos_material_month",
    "gold.corr_stock_tempo_sales_material_month",
    "gold.corr_sales_b2b_material_month",
    "gold.corr_b2b_sat_branch_month",
    "gold.corr_sat_dc_oos_material_month",
    "gold.rpt_sat_promo_material_december_semantic",
    "gold.rpt_sat_promo_material_uplift",
    "gold.rpt_sap_customer_material_month_semantic",
    "gold.rpt_sap_sales_office_material_month_semantic",
    "gold.corr_b2b_customer_branch_estore_month",
    "gold.corr_b2b_customer_material_plu_month",
    "gold.corr_b2b_branch_material_month",
    "gold.corr_service_sales_office_material_month",
    "gold.rpt_sat_promo_b2b_sellout_uplift",
    "gold.corr_service_sales_office_cust_group_material_month",
)

# Quick sample queries (governed-style sanity)
SAMPLE_QUERIES = {
    "ping": "SELECT 1 AS connection_ok",
    "branch_material_rows": "SELECT COUNT(*) AS n FROM gold.corr_b2b_branch_material_month",
    "branch_material_top3": """
        SELECT calmonth, branch, material, b2b_bill_val
        FROM gold.corr_b2b_branch_material_month
        ORDER BY b2b_bill_val DESC NULLS LAST
        LIMIT 3
    """,
    "promo_b2b_uplift_rows": "SELECT COUNT(*) AS n FROM gold.rpt_sat_promo_b2b_sellout_uplift",
    "service_office_fill_sample": """
        SELECT sales_off, material, service_fill_rate
        FROM gold.corr_service_sales_office_material_month
        WHERE service_fill_rate IS NOT NULL
        ORDER BY service_fill_rate ASC
        LIMIT 3
    """,
}


def connect():
    from impala.dbapi import connect

    return connect(
        host=IMPALA_HOST,
        port=IMPALA_PORT,
        database=IMPALA_DATABASE,
        auth_mechanism=IMPALA_AUTH_MECHANISM,
        user=IMPALA_USER or None,
        password=IMPALA_PASSWORD or None,
        use_ssl=IMPALA_USE_SSL,
        use_http_transport=IMPALA_USE_HTTP_TRANSPORT,
        http_path=IMPALA_HTTP_PATH,
        kerberos_service_name=IMPALA_KERBEROS_SERVICE_NAME,
    )


def run_sql(cur, sql: str) -> list[tuple]:
    cur.execute(sql.strip(), configuration={"QUERY_TIMEOUT_S": str(QUERY_TIMEOUT_S)})
    cols = [c[0] for c in cur.description] if cur.description else []
    rows = cur.fetchall()
    return cols, rows


def main() -> int:
    print(f"Impala {IMPALA_HOST}:{IMPALA_PORT} db={IMPALA_DATABASE} auth={IMPALA_AUTH_MECHANISM}")
    conn = connect()
    cur = conn.cursor()
    failures = 0

    try:
        print("\n=== Sample queries ===")
        for name, sql in SAMPLE_QUERIES.items():
            try:
                cols, rows = run_sql(cur, sql)
                print(f"\n[{name}]")
                print("  columns:", cols)
                for row in rows:
                    print(" ", row)
            except Exception as exc:
                failures += 1
                print(f"\n[{name}] FAIL: {exc}")

        print("\n=== OSSIE Gold sources (COUNT(*)) ===")
        for source in GOLD_SOURCES:
            try:
                _, rows = run_sql(cur, f"SELECT COUNT(*) AS row_count FROM {source}")
                count = rows[0][0] if rows else "?"
                status = "OK" if count and int(count) > 0 else "EMPTY"
                print(f"  {status:5} {count:>8}  {source}")
                if not count or int(count) <= 0:
                    failures += 1
            except Exception as exc:
                failures += 1
                print(f"  FAIL       {source}")
                print(f"             {str(exc)[:200]}")

    finally:
        cur.close()
        conn.close()

    print(f"\nDone. failures={failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())

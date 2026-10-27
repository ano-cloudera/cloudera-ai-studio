#!/usr/bin/env python3
"""Check sign/magnitude of sell_in_bill_val in gold sales-office material view vs office Q4 total."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.config import get_settings  # noqa: E402
from app.db.impala_backend import ImpalaBackend, is_impala_configured  # noqa: E402

OFFICES = ("0201", "0280")
MATERIAL = "092-27-02"
VIEW = "gold.rpt_sap_sales_office_material_month_semantic"


def main() -> int:
    get_settings.cache_clear()
    settings = get_settings()
    if not is_impala_configured(settings):
        print("Impala not configured (.env)")
        return 2
    backend = ImpalaBackend(settings)

    exists = backend.query(f"SHOW TABLES IN gold LIKE 'rpt_sap_sales_office_material%'")
    print("tables:", exists)

    office_totals = backend.query(
        """
        SELECT sales_office,
               SUM(sell_in_bill_val) AS q4_sell_in_bill_val,
               SUM(CASE WHEN sell_in_bill_val < 0 THEN 1 ELSE 0 END) AS negative_month_rows,
               COUNT(*) AS grain_rows
        FROM gold.rpt_sap_sales_office_material_month_semantic d
        WHERE d.calmonth BETWEEN 202410 AND 202412
          AND d.sales_office IN ('0201', '0280')
        GROUP BY sales_office
        ORDER BY sales_office
        """
    )
    print("\n=== Q4 totals from material view (sum all materials) ===")
    for row in office_totals:
        print(row)

    sku = backend.query(
        f"""
        SELECT sales_office, material,
               SUM(sell_in_bill_val) AS q4_val,
               MIN(sell_in_bill_val) AS min_month_val,
               MAX(sell_in_bill_val) AS max_month_val
        FROM {VIEW} d
        WHERE d.calmonth BETWEEN 202410 AND 202412
          AND d.sales_office IN ('0201', '0280')
          AND d.material = '{MATERIAL}'
        GROUP BY sales_office, material
        """
    )
    print(f"\n=== SKU {MATERIAL} ===")
    for row in sku:
        print(row)

    top = backend.query(
        """
        SELECT sales_office, material, SUM(sell_in_bill_val) AS q4_val
        FROM gold.rpt_sap_sales_office_material_month_semantic d
        WHERE d.calmonth BETWEEN 202410 AND 202412
          AND d.sales_office IN ('0201', '0280')
        GROUP BY sales_office, material
        ORDER BY q4_val DESC
        LIMIT 10
        """
    )
    print("\n=== Top 10 positive material rows (0201+0280, ORDER BY q4_val DESC) ===")
    for row in top:
        print(row)

    bottom = backend.query(
        """
        SELECT sales_office, material, SUM(sell_in_bill_val) AS q4_val
        FROM gold.rpt_sap_sales_office_material_month_semantic d
        WHERE d.calmonth BETWEEN 202410 AND 202412
          AND d.sales_office IN ('0201', '0280')
        GROUP BY sales_office, material
        ORDER BY q4_val ASC
        LIMIT 10
        """
    )
    print("\n=== Bottom 10 (most negative) material rows ===")
    for row in bottom:
        print(row)

    # Compare to corr_sales_sales_office if present
    try:
        corr = backend.query(
            """
            SELECT sales_off, SUM(bill_val) AS office_q4_total
            FROM gold.corr_sales_sales_office
            WHERE calmonth BETWEEN 202410 AND 202412
              AND sales_off IN ('0201', '0280')
            GROUP BY sales_off
            ORDER BY sales_off
            """
        )
        print("\n=== gold.corr_sales_sales_office Q4 (reference office total) ===")
        for row in corr:
            print(row)
    except Exception as exc:
        print("\n(corr_sales_sales_office skip:", type(exc).__name__, str(exc)[:120], ")")

    neg_share = backend.query(
        """
        SELECT sales_office,
               SUM(CASE WHEN sell_in_bill_val < 0 THEN sell_in_bill_val ELSE 0 END) AS sum_negative_lines,
               SUM(CASE WHEN sell_in_bill_val >= 0 THEN sell_in_bill_val ELSE 0 END) AS sum_nonneg_lines,
               SUM(sell_in_bill_val) AS net
        FROM gold.rpt_sap_sales_office_material_month_semantic d
        WHERE d.calmonth BETWEEN 202410 AND 202412
          AND d.sales_office IN ('0201', '0280')
        GROUP BY sales_office
        """
    )
    print("\n=== Negative vs non-negative line sums (material-month grain, then summed) ===")
    for row in neg_share:
        print(row)

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"FAILED: {type(exc).__name__}: {exc}")
        raise SystemExit(1) from exc

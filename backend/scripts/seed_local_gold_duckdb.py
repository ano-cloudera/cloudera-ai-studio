#!/usr/bin/env python3
"""Seed local DuckDB gold.* tables (1:1 column names with Impala/OSSIE views)."""

from __future__ import annotations

import random
import sys
from pathlib import Path

import duckdb
import yaml

BACKEND_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = BACKEND_ROOT / "data" / "local_gold_view_schemas.yaml"
DEFAULT_DB = BACKEND_ROOT / "runtime" / "tempo_gold_local.duckdb"
MONTHS = [202410, 202411, 202412]
DEFAULT_ROW_TARGET = 1000


def _duckdb_column_type(column: str) -> str:
    if column.casefold() == "calmonth_date":
        return "DATE"
    sample = _synthetic_value(column, 0, MONTHS[0])
    if isinstance(sample, bool):
        return "BOOLEAN"
    if isinstance(sample, int):
        return "INTEGER"
    if isinstance(sample, float):
        return "DOUBLE"
    return "VARCHAR"


def _synthetic_value(column: str, row_idx: int, calmonth: int) -> object:
    key = column.casefold()
    if key == "calmonth":
        return calmonth
    if key == "calmonth_date":
        year = calmonth // 100
        month = calmonth % 100
        return f"{year}-{month:02d}-01"
    if key in {"material", "sku", "material_code"}:
        return f"500-21-{(row_idx % 10):02d}"
    if key in {"sales_off", "branch", "dcname", "plant", "warehouse", "sales_office"}:
        return f"SO{(row_idx % 5) + 1:02d}"
    if key in {"customer", "cust_id", "cust_code", "cust_group", "c_0cust_grp3"}:
        return f"C{1000 + (row_idx % 20)}"
    if key.startswith("has_") or key.endswith("_flag"):
        return True
    if key in {"thn"}:
        return 2024
    if key in {"bln"}:
        return ["OCT", "NOV", "DEC"][row_idx % 3]
    if key in {"reporting_month"}:
        return calmonth
    if key in {"reporting_period"}:
        return "2024Q4"
    if key in {"period_start_calmonth"}:
        return 202410
    if key in {"period_end_calmonth"}:
        return 202412
    if key in {"reporting_grain"}:
        return "sales_office_quarter"
    if key in {"reconciliation_scope"}:
        return "shared_customer_only"
    if "ratio" in key or "rate" in key or "fill" in key or key.endswith("_pct"):
        return round(0.55 + (row_idx % 40) / 100, 4)
    if any(token in key for token in ("val", "amt", "billing", "revenue", "sales", "stock")):
        return float(1_000_000 * (100 - row_idx) * (1 + calmonth % 3))
    if any(token in key for token in ("qty", "quantity", "count", "observation", "lines", "rows", "materials", "customers")):
        return int(50 * (10 - (row_idx % 10)) + row_idx)
    if key in {"kode_plu", "plu", "material_id", "retail_plu"}:
        return f"PLU{row_idx:04d}"
    if key in {"mekanisme", "program_status", "promo_type", "division", "e_store", "ka_group"}:
        return f"VAL-{row_idx % 4 + 1}"
    if key in {"fill_rate_band"}:
        return "high_fill"
    return f"sample_{row_idx % 7}"


def _sql_literal(value: object) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        return str(value)
    escaped = str(value).replace("'", "''")
    return f"'{escaped}'"


def _table_name(source: str) -> str:
    return source.split(".", 1)[1]


def main() -> int:
    if not SCHEMA_PATH.is_file():
        print(f"Missing {SCHEMA_PATH}. Run: python backend/scripts/build_local_gold_schemas.py", file=sys.stderr)
        return 1

    row_target = DEFAULT_ROW_TARGET
    if len(sys.argv) >= 3 and sys.argv[1].isdigit():
        row_target = int(sys.argv[1])
        db_arg = sys.argv[2]
    elif len(sys.argv) == 2 and not sys.argv[1].isdigit():
        db_arg = sys.argv[1]
    else:
        db_arg = None
    db_path = Path(db_arg) if db_arg else DEFAULT_DB
    payload = yaml.safe_load(SCHEMA_PATH.read_text(encoding="utf-8"))
    views: dict = payload.get("views") or {}

    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()

    random.seed(42)
    con = duckdb.connect(str(db_path))
    con.execute("CREATE SCHEMA IF NOT EXISTS gold")

    for source in sorted(views):
        meta = views[source]
        columns: list[str] = list(meta.get("columns") or [])
        if not columns:
            continue
        table = _table_name(source)
        con.execute(f'DROP TABLE IF EXISTS gold."{table}"')
        col_sql = ", ".join(f'"{c}"' for c in columns)
        col_types = ", ".join(f'"{c}" {_duckdb_column_type(c)}' for c in columns)
        con.execute(f'CREATE TABLE gold."{table}" ({col_types})')
        placeholders = ", ".join(["?"] * len(columns))
        insert_sql = f'INSERT INTO gold."{table}" ({col_sql}) VALUES ({placeholders})'
        batch: list[tuple] = []
        for i in range(row_target):
            calmonth = MONTHS[i % len(MONTHS)]
            row = {col: _synthetic_value(col, i, calmonth) for col in columns}
            batch.append(tuple(row[c] for c in columns))
            if len(batch) >= 100:
                con.executemany(insert_sql, batch)
                batch.clear()
        if batch:
            con.executemany(insert_sql, batch)
        count = con.execute(f'SELECT COUNT(*) FROM gold."{table}"').fetchone()[0]
        ddl = "DDL" if meta.get("from_ddl") else "OSSIE"
        print(f"  {source}: {count:,} rows, {len(columns)} cols ({ddl})")

    con.close()
    print(f"DuckDB governed sample ready: {db_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

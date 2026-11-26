#!/usr/bin/env python3
"""Load the health insurance sample into the warehouse through Trino: the tables (Iceberg when the catalog is Iceberg) and the views.

Usage (backend venv, from the repo root; Trino settings from the environment or the repo's .env):
  python samples/health_insurance/load_health_insurance.py --catalog iceberg --schema demo_asuransi --probe
  python samples/health_insurance/load_health_insurance.py --catalog iceberg --schema demo_asuransi [--create-schema] [--replace]

  --probe          connect and show what is there; writes nothing
  --create-schema  create the schema when it does not exist (otherwise a missing schema stops the load)
  --replace        drop and reload a table that already has rows (otherwise such a table is left as it is)
  --only T1,T2     load only these tables (the views are always recreated)
  --views-only     only (re)create the views

The target is never assumed: --catalog and --schema (or HI_TRINO_CATALOG / HI_TRINO_SCHEMA) are required. TRINO_HOST, TRINO_USER,
TRINO_PASSWORD (empty for a local unsecured Trino), TRINO_PORT (443) and TRINO_HTTP_SCHEME (https) say where Trino is. The data is
generated first when data/ is empty (generate_data.py, deterministic). The alert tables come from scoring/score_history.py and are
loaded when their CSVs exist. Credentials are never printed. After each table the row count and, for claims, the paid total are
compared with the CSV, and a mismatch stops the load.
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
sys.path.insert(0, str(HERE))

from warehouse import TABLES, VIEW_ORDER, create_table_sql, create_view_sql, literal  # noqa: E402

BATCH = 2000


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
        if key and key not in os.environ:
            os.environ[key] = value.strip().strip('"').strip("'")


def connect(catalog: str, schema: str):
    import trino

    user = os.environ.get("TRINO_USER") or "trino"
    password = os.environ.get("TRINO_PASSWORD", "")
    return trino.dbapi.connect(
        host=os.environ["TRINO_HOST"], port=int(os.getenv("TRINO_PORT", "443")), user=user,
        http_scheme=os.getenv("TRINO_HTTP_SCHEME", "https"), catalog=catalog, schema=schema,
        auth=trino.auth.BasicAuthentication(user, password) if password else None,
    )


def main(argv: list[str] | None = None) -> int:
    load_env_file(HERE.parents[1] / ".env")
    parser = argparse.ArgumentParser(description="Load the health insurance sample into Trino.")
    parser.add_argument("--catalog", default=os.getenv("HI_TRINO_CATALOG"))
    parser.add_argument("--schema", default=os.getenv("HI_TRINO_SCHEMA"))
    parser.add_argument("--probe", action="store_true")
    parser.add_argument("--create-schema", action="store_true")
    parser.add_argument("--replace", action="store_true")
    parser.add_argument("--only", default="")
    parser.add_argument("--views-only", action="store_true")
    args = parser.parse_args(argv)
    if not args.catalog or not args.schema:
        print("Say where to load: --catalog and --schema (or HI_TRINO_CATALOG / HI_TRINO_SCHEMA). Nothing was written.", file=sys.stderr)
        return 2
    if not os.environ.get("TRINO_HOST"):
        print("TRINO_HOST is not set. Nothing was written.", file=sys.stderr)
        return 2

    conn = connect(args.catalog, args.schema)
    cur = conn.cursor()

    def run(sql: str):
        cur.execute(sql)
        return cur.fetchall()

    prefix = f'"{args.catalog}"."{args.schema}"'
    connector = run(f"SELECT connector_name FROM system.metadata.catalogs WHERE catalog_name = '{args.catalog}'")
    if not connector:
        print(f"Catalog {args.catalog} does not exist in this Trino. Nothing was written.", file=sys.stderr)
        return 2
    iceberg = connector[0][0] == "iceberg"
    schemas = {r[0] for r in run(f'SHOW SCHEMAS FROM "{args.catalog}"')}
    print(f"[TARGET] {args.catalog}.{args.schema} (connector {connector[0][0]}{', tables as Iceberg/Parquet' if iceberg else ''})")

    if args.probe:
        if args.schema not in schemas:
            print(f"[PROBE] schema {args.schema} does not exist yet (load with --create-schema)")
            return 0
        tables = [r[0] for r in run(f"SHOW TABLES FROM {prefix}")]
        print("[PROBE] tables:", ", ".join(tables) or "none")
        for table in [t for t in TABLES if t in tables]:
            print(f"[PROBE] {table}: {run(f'SELECT count(*) FROM {prefix}.{table}')[0][0]:,} rows")
        return 0

    if args.schema not in schemas:
        if not args.create_schema:
            print(f"Schema {args.catalog}.{args.schema} does not exist. Add --create-schema to create it. Nothing was written.", file=sys.stderr)
            return 2
        run(f"CREATE SCHEMA {prefix}")
        print(f"[SCHEMA] created {args.catalog}.{args.schema}")

    if not args.views_only:
        if not (DATA / "klaim.csv").exists():
            print("[DATA] generating the sample data (deterministic, about 10 seconds)")
            import generate_data

            generate_data.main([])
        wanted = [t.strip() for t in args.only.split(",") if t.strip()] or list(TABLES)
        existing = {r[0] for r in run(f"SHOW TABLES FROM {prefix}")}
        for table in wanted:
            csv_name, columns, _ = TABLES[table]
            path = DATA / csv_name
            fq = f"{prefix}.{table}"
            if not path.exists():
                if table in existing:
                    print(f"[SKIP] {table}: {csv_name} not found; the table is left as it is")
                else:
                    run(create_table_sql(prefix, table, iceberg))  # empty, so the views exist and a stream can append to it
                    print(f"[EMPTY] {table}: created without rows ({csv_name} comes from scoring/score_history.py)")
                continue
            if table in existing:
                rows = run(f"SELECT count(*) FROM {fq}")[0][0]
                if rows and not args.replace:
                    print(f"[SKIP] {table} already has {rows:,} rows (use --replace to reload it)")
                    continue
                run(f"DROP TABLE {fq}")
            run(create_table_sql(prefix, table, iceberg))
            with path.open(newline="", encoding="utf-8") as fh:
                data = list(csv.DictReader(fh))
            started = time.monotonic()
            for i in range(0, len(data), BATCH):
                values = ",".join("(" + ",".join(literal(r[n], t) for n, t in columns) + ")" for r in data[i : i + BATCH])
                run(f"INSERT INTO {fq} VALUES {values}")
                if len(data) > 50_000 and (i // BATCH) % 25 == 0:
                    print(f"   {table}: {min(i + BATCH, len(data)):,} / {len(data):,}", flush=True)
            count = run(f"SELECT count(*) FROM {fq}")[0][0]
            if count != len(data):
                print(f"[FAILED] {table}: {len(data):,} csv rows but {count:,} in Trino", file=sys.stderr)
                return 1
            note = ""
            if table == "hi_klaim":
                expected = sum(int(r["jumlah_dibayar_idr"]) for r in data)
                got = run(f"SELECT SUM(jumlah_dibayar_idr) FROM {fq}")[0][0]
                if got != expected:
                    print(f"[FAILED] hi_klaim: paid total {got:,} in Trino, {expected:,} in the csv", file=sys.stderr)
                    return 1
                note = f", paid IDR {got:,} matches"
            print(f"[LOAD] {table}: {count:,} rows in {time.monotonic() - started:.0f}s{note}", flush=True)
            if iceberg and len(data) > 50_000:
                run(f"ALTER TABLE {fq} EXECUTE optimize")  # the batches left many small files
                print(f"[OPTIMIZE] {table}: small files compacted")

    present = {r[0] for r in run(f"SHOW TABLES FROM {prefix}")}
    for view in VIEW_ORDER:
        needs = {"v_hi_alert": {"hi_alert", "hi_hasil_investigasi"}, "v_hi_klaim": {"hi_klaim", "hi_alert"}, "v_hi_rasio_klaim": {"hi_premi_bulanan"}}[view]
        if not needs <= present:
            print(f"[SKIP] {view}: needs {', '.join(sorted(needs - present))} first")
            continue
        run(create_view_sql(prefix, view))
        started = time.monotonic()
        rows = run(f"SELECT count(*) FROM {prefix}.{view}")[0][0]
        print(f"[VIEW] {view}: {rows:,} rows ({time.monotonic() - started:.1f}s to count)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

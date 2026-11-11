#!/usr/bin/env python3
"""Load the synthetic fuel distribution data into Trino: four Iceberg tables and one governed view (quota against realised volume).

Usage (backend venv, from the repo root; the Trino settings come from the environment or from the repo's .env):
  python samples/fuel_distribution/load_fuel_distribution.py [--replace] [--probe]
  --probe   only connect and list what is there (reads, writes nothing)
TRINO_CATALOG / TRINO_SCHEMA default to iceberg / default. Use the iceberg catalog: the hive catalog shares its metastore and lists
the same names but cannot read an Iceberg table.
Refuses to touch a table that already has rows unless --replace is given (then it drops and recreates it).
Rows go in large batches (a few dozen commits) so the metastore is not flooded. Credentials are never printed.
"""
from __future__ import annotations

import csv
import os
import sys
from pathlib import Path

import trino

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
BATCH = 2500

TABLES = {  # table -> (csv file, columns)
    "fuel_customers": ("customers.csv", [
        ("kode_pelanggan", "VARCHAR"), ("segmen_bisnis", "VARCHAR"), ("nama_tipe_pelanggan", "VARCHAR"), ("regional", "VARCHAR"),
        ("provinsi", "VARCHAR"), ("fuel_terminal", "VARCHAR"), ("jarak_standar_km", "DOUBLE"),
    ]),
    "fuel_deliveries": ("deliveries.csv", [
        ("id_lo", "VARCHAR"), ("tanggal_transaksi", "DATE"), ("segmen_bisnis", "VARCHAR"), ("regional", "VARCHAR"), ("provinsi", "VARCHAR"),
        ("fuel_terminal", "VARCHAR"), ("kode_pelanggan", "VARCHAR"), ("nama_tipe_pelanggan", "VARCHAR"), ("produk", "VARCHAR"),
        ("kategori_bbm", "VARCHAR"), ("volume_kl", "INTEGER"), ("harga_per_liter_idr", "INTEGER"), ("total_nilai_idr", "BIGINT"),
        ("nopol_mobil_tangki", "VARCHAR"), ("kapasitas_tangki_kl", "INTEGER"), ("jarak_tempuh_km", "DOUBLE"),
        ("durasi_kirim_menit", "INTEGER"), ("sla_menit", "INTEGER"), ("status_pengiriman", "VARCHAR"),
    ]),
    "fuel_quota": ("quota.csv", [("regional", "VARCHAR"), ("produk", "VARCHAR"), ("bulan", "DATE"), ("kuota_kl", "INTEGER")]),
    "fuel_terminals": ("terminals.csv", [
        ("fuel_terminal", "VARCHAR"), ("regional", "VARCHAR"), ("kota", "VARCHAR"), ("latitude", "DOUBLE"), ("longitude", "DOUBLE"),
    ]),
}

VIEW = """CREATE OR REPLACE VIEW "{catalog}"."{schema}"."v_fuel_quota_attainment" AS
SELECT q.regional, q.produk, q.bulan, q.kuota_kl, COALESCE(d.realisasi_kl, 0) AS realisasi_kl
FROM "{catalog}"."{schema}"."fuel_quota" q
LEFT JOIN (
  SELECT regional, produk, date_trunc('month', tanggal_transaksi) AS bulan, SUM(volume_kl) AS realisasi_kl
  FROM "{catalog}"."{schema}"."fuel_deliveries"
  WHERE segmen_bisnis = 'Ritel_SPBU'
  GROUP BY 1, 2, 3
) d ON q.regional = d.regional AND q.produk = d.produk AND q.bulan = d.bulan"""


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
    return value  # INTEGER / BIGINT / DOUBLE


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
        print(f"[LOAD] {table}: {len(data)} csv rows, trino count={run(f'SELECT count(*) FROM {fq}')[0][0]}", flush=True)
    run(VIEW.format(catalog=catalog, schema=schema))
    view_count = run(f'SELECT count(*) FROM "{catalog}"."{schema}"."v_fuel_quota_attainment"')[0][0]
    print(f"[VIEW] v_fuel_quota_attainment: {view_count} rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""The answer key of the demo questions, computed in the warehouse through Trino, and a check that every planted pattern shows there.

Usage (after load_health_insurance.py; same settings):
  python samples/health_insurance/expected_answers.py --catalog iceberg --schema demo_asuransi

Each question of the demo (judge_demo.json) is answered here with plain SQL on the same views the semantic model reads. A pattern that
does not come out as planted ends the script with exit code 1, so a load that went wrong is caught before anyone asks a question.
Reads only.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from load_health_insurance import connect, load_env_file  # noqa: E402

FAILED: list[str] = []


def check(ok: bool, label: str) -> None:
    print(f"   {'PASS' if ok else 'FAIL'}  {label}")
    if not ok:
        FAILED.append(label)


def rp(value: float) -> str:
    return f"Rp {value:,.0f}".replace(",", ".")


def main(argv: list[str] | None = None) -> int:
    load_env_file(HERE.parents[1] / ".env")
    parser = argparse.ArgumentParser(description="Answer key of the health insurance demo, from the warehouse.")
    parser.add_argument("--catalog", default=os.getenv("HI_TRINO_CATALOG"))
    parser.add_argument("--schema", default=os.getenv("HI_TRINO_SCHEMA"))
    args = parser.parse_args(argv)
    if not args.catalog or not args.schema:
        print("Say where the data is: --catalog and --schema (or HI_TRINO_CATALOG / HI_TRINO_SCHEMA).", file=sys.stderr)
        return 2
    cur = connect(args.catalog, args.schema).cursor()
    t = f'"{args.catalog}"."{args.schema}"'

    def q(sql: str) -> list[tuple]:
        cur.execute(sql.format(t=t))
        return cur.fetchall()

    print("1. Overall")
    claims, paid, alerts = q("SELECT count(*), sum(jumlah_dibayar_idr), count(id_alert) FROM {t}.v_hi_klaim")[0]
    print(f"   claims {claims:,}; paid {rp(paid)}; alerts {alerts:,} ({alerts / claims:.2%} of claims)")
    ratio = q("SELECT sum(klaim_dibayar_idr) * 100.0 / sum(premi_idr) FROM {t}.v_hi_rasio_klaim")[0][0]
    print(f"   claim ratio (paid claims over earned premium): {ratio:.2f}%")
    for produk, r in q("SELECT produk, sum(klaim_dibayar_idr) * 100.0 / sum(premi_idr) FROM {t}.v_hi_rasio_klaim GROUP BY 1 ORDER BY 2 DESC"):
        print(f"      {produk}: {r:.2f}%")

    print("2. Alerts by month (value of alerted claims)")
    for month, n, value in q("""SELECT date_format(tanggal_masuk, '%Y-%m'), count(*), sum(jumlah_tagihan_idr) FROM {t}.v_hi_klaim
                                WHERE id_alert IS NOT NULL AND tanggal_masuk >= DATE '2026-08-01' GROUP BY 1 ORDER BY 1"""):
        print(f"   {month}: {n:,} alerted claims, billed {rp(value)}")

    print("3. Providers with the most alerted claims")
    top = q("""SELECT nama_penyedia, count(id_alert), count(*) FROM {t}.v_hi_klaim GROUP BY 1 HAVING count(id_alert) > 0
               ORDER BY 2 DESC LIMIT 5""")
    for name, n, total in top:
        print(f"   {name}: {n:,} alerted of {total:,} claims")
    check(top[0][0] == "RS Demo Kenanga Surabaya", "the most alerted provider is RS Demo Kenanga Surabaya (volume_dokter)")
    check({r[0] for r in top[:3]} >= {"RS Demo Cendana Bekasi"}, "RS Demo Cendana Bekasi is in the top 3 (upcoding)")

    print("4. Average inpatient bill per class B hospital (upcoding)")
    rows = q("""SELECT nama_penyedia, avg(jumlah_tagihan_idr), count(*) FROM {t}.v_hi_klaim
                WHERE jenis_layanan = 'Rawat Inap' AND kelas_penyedia = 'Kelas B' GROUP BY 1 HAVING count(*) >= 100 ORDER BY 2 DESC""")
    others = [r[1] for r in rows if r[0] != "RS Demo Cendana Bekasi"]
    cendana = next(r[1] for r in rows if r[0] == "RS Demo Cendana Bekasi")
    print(f"   first: {rows[0][0]} {rp(rows[0][1])}; second: {rows[1][0]} {rp(rows[1][1])}; class B average of the others {rp(sum(others) / len(others))}")
    check(rows[0][0] == "RS Demo Cendana Bekasi", "Cendana has the highest average inpatient bill among class B hospitals")
    check(cendana > 1.25 * sum(others) / len(others), "Cendana bills at least 25% more than the other class B hospitals")
    for code in ("A91", "J18.9"):
        mine, peers = q(f"""SELECT avg(CASE WHEN nama_penyedia = 'RS Demo Cendana Bekasi' THEN jumlah_tagihan_idr END),
                                   avg(CASE WHEN nama_penyedia <> 'RS Demo Cendana Bekasi' THEN jumlah_tagihan_idr END)
                            FROM {{t}}.v_hi_klaim WHERE jenis_layanan = 'Rawat Inap' AND kelas_penyedia = 'Kelas B' AND kode_diagnosis = '{code}'""")[0]
        print(f"   {code}: Cendana {rp(mine)} vs other class B {rp(peers)} ({mine / peers - 1:+.0%})")

    print("5. Doctors with the most claims per working day")
    rows = q("""SELECT kode_dokter, nama_penyedia, count(*) * 1.0 / count(DISTINCT tanggal_masuk), count(*) FROM {t}.v_hi_klaim
                WHERE jenis_layanan = 'Rawat Jalan' GROUP BY 1, 2 HAVING count(*) >= 50 ORDER BY 3 DESC LIMIT 3""")
    for code, name, rate, n in rows:
        print(f"   {code} ({name}): {rate:.1f} claims per working day, {n:,} claims")
    check(rows[0][1] == "RS Demo Kenanga Surabaya" and rows[0][2] > 5 * rows[1][2], "one Kenanga doctor has far more claims per day than any other")

    print("6. Bank accounts shared by several members (jaringan)")
    rows = q("""SELECT rekening_penggantian_hash, count(DISTINCT id_peserta), count(*), sum(jumlah_dibayar_idr) FROM {t}.v_hi_klaim
                WHERE rekening_penggantian_hash IS NOT NULL GROUP BY 1 ORDER BY 2 DESC LIMIT 7""")
    for account, members, n, value in rows:
        print(f"   {account}: {members} members, {n} claims, paid {rp(value)}")
    shared = q("""SELECT count(DISTINCT rekening_penggantian_hash), count(DISTINCT id_peserta), count(*), sum(jumlah_dibayar_idr),
                         count(DISTINCT nama_penyedia), count(DISTINCT kode_dokter)
                  FROM {t}.v_hi_klaim WHERE rekening_dipakai_bersama = 'Rekening dipakai bersama'""")[0]
    print(f"   shared accounts: {shared[0]} accounts, {shared[1]} members, {shared[2]} claims, paid {rp(shared[3])}, "
          f"{shared[4]} provider(s), {shared[5]} doctor(s)")
    check(shared[0] == 6 and shared[4] == 1 and shared[5] == 1, "the shared accounts are exactly the 6 of the ring, at one clinic, with one doctor")
    where = q("""SELECT nama_penyedia, jenis_hari, waktu_kunjungan, count(*) FROM {t}.v_hi_klaim WHERE rekening_dipakai_bersama = 'Rekening dipakai bersama'
                 GROUP BY 1, 2, 3 ORDER BY 4 DESC LIMIT 2""")
    print("   where and when:", "; ".join(f"{a}, {b}, {c}: {n}" for a, b, c, n in where))
    avg_ring, avg_all = q("""SELECT avg(CASE WHEN rekening_dipakai_bersama = 'Rekening dipakai bersama' THEN jumlah_tagihan_idr END),
                                    avg(CASE WHEN rekening_dipakai_bersama <> 'Rekening dipakai bersama' THEN jumlah_tagihan_idr END)
                             FROM {t}.v_hi_klaim WHERE jenis_layanan = 'Rawat Jalan'""")[0]
    print(f"   outpatient bill: shared accounts {rp(avg_ring)} vs the rest {rp(avg_all)} ({avg_ring / avg_all:.1f}x)")

    print("7. Length of stay for appendicitis (lama_rawat)")
    rows = q("""SELECT nama_penyedia, avg(lama_rawat_hari), count(*) FROM {t}.v_hi_klaim WHERE kode_diagnosis = 'K35.8'
                GROUP BY 1 HAVING count(*) >= 10 ORDER BY 2 DESC LIMIT 3""")
    overall = q("SELECT avg(lama_rawat_hari) FROM {t}.v_hi_klaim WHERE kode_diagnosis = 'K35.8'")[0][0]
    for name, days, n in rows:
        print(f"   {name}: {days:.1f} days ({n} stays)")
    print(f"   all hospitals: {overall:.1f} days")
    check(rows[0][0] == "RS Demo Flamboyan Medan", "Flamboyan keeps appendicitis patients longest")

    print("8. Second claims of one visit and readmissions")
    dup, readm = q("""SELECT count_if(klaim_ganda = 'Klaim ganda'), count_if(rawat_ulang_7_hari = 'Rawat ulang 7 hari') FROM {t}.v_hi_klaim""")[0]
    print(f"   claims in a duplicated visit: {dup:,}; readmissions within 7 days: {readm:,}")
    top_readm = q("""SELECT nama_penyedia, count_if(rawat_ulang_7_hari = 'Rawat ulang 7 hari') * 100.0 / count(*) FROM {t}.v_hi_klaim
                     WHERE jenis_layanan = 'Rawat Inap' GROUP BY 1 HAVING count(*) >= 200 ORDER BY 2 DESC LIMIT 2""")
    print("   readmission rate:", "; ".join(f"{n} {r:.1f}%" for n, r in top_readm))
    check(top_readm[0][0] == "RS Demo Tanjung Makassar", "Tanjung Makassar has the highest readmission rate")

    print("9. Investigations")
    rows = q("SELECT status_investigasi, count(*) FROM {t}.v_hi_alert GROUP BY 1 ORDER BY 2 DESC")
    print("   " + "; ".join(f"{s} {n:,}" for s, n in rows))
    confirmed = dict(rows)
    precision = confirmed["Terbukti fraud"] * 100.0 / (confirmed["Terbukti fraud"] + confirmed["Bukan fraud"])
    print(f"   confirmed share of closed investigations: {precision:.2f}%")
    loss = q("SELECT sum(jumlah_dibayar_idr) FROM {t}.v_hi_klaim WHERE status_investigasi = 'Terbukti fraud'")[0][0]
    open_value = q("""SELECT sum(jumlah_tagihan_idr) FROM {t}.v_hi_klaim WHERE tingkat_risiko = 'Tinggi'
                      AND status_investigasi IN ('Belum diperiksa', 'Sedang diperiksa')""")[0][0]
    print(f"   paid on claims confirmed as fraud: {rp(loss)}; billed on high-risk claims not yet concluded: {rp(open_value)}")

    print("10. Dengue (legitimate outbreak, January-March 2026)")
    rows = q("""SELECT date_format(tanggal_masuk, '%Y-%m'), count(*) FROM {t}.v_hi_klaim WHERE kode_diagnosis IN ('A90', 'A91')
                AND (tanggal_masuk BETWEEN DATE '2025-01-01' AND DATE '2025-03-31' OR tanggal_masuk BETWEEN DATE '2026-01-01' AND DATE '2026-03-31')
                GROUP BY 1 ORDER BY 1""")
    print("   " + "; ".join(f"{m} {n:,}" for m, n in rows))
    spread = q("""SELECT count(DISTINCT nama_penyedia), max(n) * 100.0 / sum(n) FROM (
                    SELECT nama_penyedia, count(*) AS n FROM {t}.v_hi_klaim WHERE kode_diagnosis IN ('A90', 'A91')
                    AND tanggal_masuk BETWEEN DATE '2026-01-01' AND DATE '2026-03-31' GROUP BY 1)""")[0]
    print(f"   Jan-Mar 2026: dengue claims at {spread[0]} providers; the largest has {spread[1]:.1f}% of them")
    early_2025 = sum(n for m, n in rows if m.startswith("2025"))
    early_2026 = sum(n for m, n in rows if m.startswith("2026"))
    check(early_2026 > 2 * early_2025 and spread[1] < 10, "the outbreak doubles dengue claims and is spread over many providers")

    print("\n" + ("All patterns show in the warehouse." if not FAILED else f"{len(FAILED)} check(s) failed: " + "; ".join(FAILED)))
    return 1 if FAILED else 0


if __name__ == "__main__":
    raise SystemExit(main())

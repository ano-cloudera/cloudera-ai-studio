"""The warehouse side of the health insurance sample: tables, views and the SQL that builds them, in one place.

Every table is append-only (a later fact is a new row, never an update), so a streaming writer such as NiFi only ever adds rows. The
analysis reads views: they join the tables and compute the network features (how many members share a bank account, how many claims
a doctor has on one day, a second claim of the same visit, a readmission), so rows that arrive later are part of every answer.
"""
from __future__ import annotations

# table -> (csv file in data/ or None for a table only a stream fills, columns, Iceberg partitioning or None)
TABLES: dict[str, tuple[str | None, list[tuple[str, str]], list[str] | None]] = {
    "hi_peserta": ("peserta.csv", [
        ("id_peserta", "VARCHAR"), ("id_polis", "VARCHAR"), ("produk", "VARCHAR"), ("segmen", "VARCHAR"), ("pemegang_polis", "VARCHAR"),
        ("jenis_kelamin", "VARCHAR"), ("kelompok_usia", "VARCHAR"), ("provinsi", "VARCHAR"), ("kota", "VARCHAR"), ("tanggal_mulai", "DATE"),
        ("status_polis", "VARCHAR"), ("telepon_hash", "VARCHAR"), ("rekening_hash", "VARCHAR"),
    ], None),
    "hi_penyedia": ("penyedia.csv", [
        ("kode_penyedia", "VARCHAR"), ("nama_penyedia", "VARCHAR"), ("tipe_penyedia", "VARCHAR"), ("kelas", "VARCHAR"),
        ("status_rekanan", "VARCHAR"), ("provinsi", "VARCHAR"), ("kota", "VARCHAR"), ("latitude", "DOUBLE"), ("longitude", "DOUBLE"),
    ], None),
    "hi_dokter": ("dokter.csv", [
        ("kode_dokter", "VARCHAR"), ("nama_dokter", "VARCHAR"), ("spesialisasi", "VARCHAR"), ("kode_penyedia", "VARCHAR"),
    ], None),
    "hi_diagnosis": ("diagnosis.csv", [
        ("kode_diagnosis", "VARCHAR"), ("nama_diagnosis", "VARCHAR"), ("kelompok_diagnosis", "VARCHAR"),
    ], None),
    "hi_klaim": ("klaim.csv", [
        ("id_klaim", "VARCHAR"), ("id_peserta", "VARCHAR"), ("kode_penyedia", "VARCHAR"), ("kode_dokter", "VARCHAR"),
        ("tanggal_masuk", "DATE"), ("tanggal_keluar", "DATE"), ("jam_kunjungan", "INTEGER"), ("tanggal_pengajuan", "DATE"),
        ("tanggal_keputusan", "DATE"), ("jenis_layanan", "VARCHAR"), ("kode_diagnosis", "VARCHAR"), ("tindakan_utama", "VARCHAR"),
        ("lama_rawat_hari", "INTEGER"), ("jumlah_tagihan_idr", "BIGINT"), ("jumlah_disetujui_idr", "BIGINT"), ("jumlah_dibayar_idr", "BIGINT"),
        ("metode_klaim", "VARCHAR"), ("rekening_penggantian_hash", "VARCHAR"), ("status_klaim", "VARCHAR"), ("alasan_penolakan", "VARCHAR"),
    ], ["month(tanggal_masuk)"]),
    "hi_premi_bulanan": ("premi_bulanan.csv", [
        ("bulan", "DATE"), ("produk", "VARCHAR"), ("segmen", "VARCHAR"), ("jumlah_peserta_aktif", "INTEGER"), ("premi_idr", "BIGINT"),
    ], None),
    # Written by the scoring step (scoring/score_history.py, later the streaming flow): one row per alert, never changed.
    "hi_alert": ("alert.csv", [
        ("id_alert", "VARCHAR"), ("id_klaim", "VARCHAR"), ("waktu_alert", "TIMESTAMP(3)"), ("skor_fraud", "DOUBLE"), ("tingkat_risiko", "VARCHAR"),
        ("alasan_1", "VARCHAR"), ("alasan_2", "VARCHAR"), ("alasan_3", "VARCHAR"), ("versi_model", "VARCHAR"),
    ], None),
    # Filled only by the NiFi flow (claims as they arrive, and the alerts the scoring API raises for them); the views add them to the history.
    "hi_klaim_baru": (None, [
        ("id_klaim", "VARCHAR"), ("id_peserta", "VARCHAR"), ("kode_penyedia", "VARCHAR"), ("kode_dokter", "VARCHAR"),
        ("tanggal_masuk", "DATE"), ("tanggal_keluar", "DATE"), ("jam_kunjungan", "INTEGER"), ("tanggal_pengajuan", "DATE"),
        ("tanggal_keputusan", "DATE"), ("jenis_layanan", "VARCHAR"), ("kode_diagnosis", "VARCHAR"), ("tindakan_utama", "VARCHAR"),
        ("lama_rawat_hari", "INTEGER"), ("jumlah_tagihan_idr", "BIGINT"), ("jumlah_disetujui_idr", "BIGINT"), ("jumlah_dibayar_idr", "BIGINT"),
        ("metode_klaim", "VARCHAR"), ("rekening_penggantian_hash", "VARCHAR"), ("status_klaim", "VARCHAR"), ("alasan_penolakan", "VARCHAR"),
    ], ["month(tanggal_masuk)"]),
    "hi_alert_baru": (None, [
        ("id_alert", "VARCHAR"), ("id_klaim", "VARCHAR"), ("waktu_alert", "TIMESTAMP(3)"), ("skor_fraud", "DOUBLE"), ("tingkat_risiko", "VARCHAR"),
        ("alasan_1", "VARCHAR"), ("alasan_2", "VARCHAR"), ("alasan_3", "VARCHAR"), ("versi_model", "VARCHAR"),
    ], None),
    # The investigators' findings, appended as they come; the latest per alert counts.
    "hi_hasil_investigasi": ("hasil_investigasi.csv", [
        ("id_alert", "VARCHAR"), ("waktu_hasil", "TIMESTAMP(3)"), ("status_investigasi", "VARCHAR"), ("catatan", "VARCHAR"),
    ], None),
}

# The views the semantic model reads. {t} is the quoted catalog.schema prefix.
VIEWS: dict[str, str] = {
    # The history and what the stream has added since: every other view reads these two, so a claim that arrives is part of every answer.
    "v_hi_klaim_gabungan": """
SELECT id_klaim, id_peserta, kode_penyedia, kode_dokter, tanggal_masuk, tanggal_keluar, jam_kunjungan, tanggal_pengajuan, tanggal_keputusan, jenis_layanan, kode_diagnosis, tindakan_utama, lama_rawat_hari, jumlah_tagihan_idr, jumlah_disetujui_idr, jumlah_dibayar_idr, metode_klaim, rekening_penggantian_hash, status_klaim, alasan_penolakan
FROM {t}.hi_klaim
UNION ALL
SELECT id_klaim, id_peserta, kode_penyedia, kode_dokter, tanggal_masuk, tanggal_keluar, jam_kunjungan, tanggal_pengajuan, tanggal_keputusan, jenis_layanan, kode_diagnosis, tindakan_utama, lama_rawat_hari, jumlah_tagihan_idr, jumlah_disetujui_idr, jumlah_dibayar_idr, metode_klaim, rekening_penggantian_hash, status_klaim, alasan_penolakan
FROM {t}.hi_klaim_baru""",
    "v_hi_alert_gabungan": """
SELECT id_alert, id_klaim, waktu_alert, skor_fraud, tingkat_risiko, alasan_1, alasan_2, alasan_3, versi_model
FROM {t}.hi_alert
UNION ALL
SELECT id_alert, id_klaim, waktu_alert, skor_fraud, tingkat_risiko, alasan_1, alasan_2, alasan_3, versi_model
FROM {t}.hi_alert_baru""",
    "v_hi_alert": """
SELECT a.id_alert, a.id_klaim, a.waktu_alert, CAST(a.waktu_alert AS DATE) AS tanggal_alert, a.skor_fraud, a.tingkat_risiko,
       a.alasan_1, a.alasan_2, a.alasan_3, a.versi_model,
       COALESCE(h.status_investigasi, 'Belum diperiksa') AS status_investigasi, h.waktu_hasil
FROM {t}.v_hi_alert_gabungan a
LEFT JOIN (
  SELECT id_alert, status_investigasi, waktu_hasil,
         row_number() OVER (PARTITION BY id_alert ORDER BY waktu_hasil DESC) AS urutan
  FROM {t}.hi_hasil_investigasi
) h ON h.id_alert = a.id_alert AND h.urutan = 1""",
    "v_hi_klaim": """
WITH rekening AS (
  SELECT rekening_penggantian_hash, COUNT(DISTINCT id_peserta) AS peserta_per_rekening
  FROM {t}.v_hi_klaim_gabungan
  WHERE rekening_penggantian_hash IS NOT NULL AND rekening_penggantian_hash <> ''
  GROUP BY rekening_penggantian_hash
),
telepon AS (
  SELECT telepon_hash, COUNT(*) AS peserta_per_telepon FROM {t}.hi_peserta GROUP BY telepon_hash
),
klaim AS (
  SELECT k.*,
         COUNT(*) OVER (PARTITION BY k.kode_dokter, k.tanggal_masuk) AS klaim_dokter_hari_itu,
         min(k.kode_penyedia) OVER (PARTITION BY k.id_peserta, k.tanggal_masuk, k.kode_diagnosis) AS penyedia_pertama,
         max(k.kode_penyedia) OVER (PARTITION BY k.id_peserta, k.tanggal_masuk, k.kode_diagnosis) AS penyedia_terakhir,
         lag(k.tanggal_keluar) OVER (PARTITION BY k.id_peserta, k.kode_diagnosis, k.jenis_layanan ORDER BY k.tanggal_masuk, k.id_klaim) AS keluar_sebelumnya
  FROM {t}.v_hi_klaim_gabungan k
)
SELECT k.id_klaim, k.id_peserta, k.tanggal_masuk, k.tanggal_keluar, k.tanggal_pengajuan, k.tanggal_keputusan, k.jam_kunjungan,
       CASE day_of_week(k.tanggal_masuk) WHEN 1 THEN 'Senin' WHEN 2 THEN 'Selasa' WHEN 3 THEN 'Rabu' WHEN 4 THEN 'Kamis'
            WHEN 5 THEN 'Jumat' WHEN 6 THEN 'Sabtu' ELSE 'Minggu' END AS hari_kunjungan,
       CASE WHEN day_of_week(k.tanggal_masuk) >= 6 THEN 'Akhir pekan' ELSE 'Hari kerja' END AS jenis_hari,
       CASE WHEN k.jam_kunjungan >= 18 OR k.jam_kunjungan < 6 THEN 'Malam' ELSE 'Siang' END AS waktu_kunjungan,
       k.jenis_layanan, k.kode_diagnosis, d.nama_diagnosis, d.kelompok_diagnosis, k.tindakan_utama, k.lama_rawat_hari,
       k.jumlah_tagihan_idr, k.jumlah_disetujui_idr, k.jumlah_dibayar_idr, k.metode_klaim, k.status_klaim, k.alasan_penolakan,
       date_diff('day', k.tanggal_keluar, k.tanggal_pengajuan) AS hari_sampai_pengajuan,
       date_diff('day', k.tanggal_pengajuan, k.tanggal_keputusan) AS hari_sampai_keputusan,
       k.kode_penyedia, p.nama_penyedia, p.tipe_penyedia,
       CASE WHEN p.tipe_penyedia = 'Rumah Sakit' THEN 'Kelas ' || p.kelas ELSE 'Klinik ' || p.kelas END AS kelas_penyedia,
       p.status_rekanan, p.provinsi, p.kota,
       k.kode_dokter, dr.spesialisasi,
       ps.produk, ps.segmen, ps.kelompok_usia, ps.jenis_kelamin,
       k.rekening_penggantian_hash, COALESCE(r.peserta_per_rekening, 0) AS peserta_per_rekening,
       CASE WHEN k.rekening_penggantian_hash IS NULL OR k.rekening_penggantian_hash = '' THEN 'Tanpa rekening (Cashless)'
            WHEN r.peserta_per_rekening >= 3 THEN 'Rekening dipakai bersama' ELSE 'Rekening sendiri' END AS rekening_dipakai_bersama,
       ps.telepon_hash, COALESCE(tl.peserta_per_telepon, 0) AS peserta_per_telepon,
       CASE WHEN tl.peserta_per_telepon >= 3 THEN 'Telepon dipakai bersama' ELSE 'Telepon sendiri' END AS telepon_dipakai_bersama,
       k.klaim_dokter_hari_itu,
       CASE WHEN k.penyedia_pertama <> k.penyedia_terakhir THEN 'Klaim ganda' ELSE 'Bukan klaim ganda' END AS klaim_ganda,  -- one visit, two providers
       CASE WHEN k.jenis_layanan = 'Rawat Inap' AND date_diff('day', k.keluar_sebelumnya, k.tanggal_masuk) BETWEEN 0 AND 7
            THEN 'Rawat ulang 7 hari' ELSE 'Bukan rawat ulang' END AS rawat_ulang_7_hari,
       a.id_alert, a.skor_fraud, COALESCE(a.tingkat_risiko, 'Tidak ada alert') AS tingkat_risiko, a.alasan_1 AS alasan_alert,
       COALESCE(a.status_investigasi, 'Tidak ada alert') AS status_investigasi
FROM klaim k
JOIN {t}.hi_penyedia p ON p.kode_penyedia = k.kode_penyedia
JOIN {t}.hi_dokter dr ON dr.kode_dokter = k.kode_dokter
JOIN {t}.hi_diagnosis d ON d.kode_diagnosis = k.kode_diagnosis
JOIN {t}.hi_peserta ps ON ps.id_peserta = k.id_peserta
LEFT JOIN rekening r ON r.rekening_penggantian_hash = k.rekening_penggantian_hash
LEFT JOIN telepon tl ON tl.telepon_hash = ps.telepon_hash
LEFT JOIN {t}.v_hi_alert a ON a.id_klaim = k.id_klaim""",
    "v_hi_rasio_klaim": """
SELECT pr.bulan, pr.produk, pr.segmen, pr.jumlah_peserta_aktif, pr.premi_idr, COALESCE(k.klaim_dibayar_idr, 0) AS klaim_dibayar_idr
FROM {t}.hi_premi_bulanan pr
LEFT JOIN (
  SELECT date_trunc('month', k.tanggal_masuk) AS bulan, ps.produk, SUM(k.jumlah_dibayar_idr) AS klaim_dibayar_idr
  FROM {t}.v_hi_klaim_gabungan k JOIN {t}.hi_peserta ps ON ps.id_peserta = k.id_peserta
  GROUP BY 1, 2
) k ON k.bulan = pr.bulan AND k.produk = pr.produk""",
}
VIEW_ORDER = ["v_hi_klaim_gabungan", "v_hi_alert_gabungan", "v_hi_alert", "v_hi_klaim", "v_hi_rasio_klaim"]  # each reads the ones before it


def create_table_sql(prefix: str, table: str, iceberg: bool) -> str:
    _, columns, partitioning = TABLES[table]
    body = ", ".join(f"{name} {kind}" for name, kind in columns)
    props = []
    if iceberg:
        props.append("format = 'PARQUET'")
        if partitioning:
            props.append("partitioning = ARRAY[" + ", ".join(f"'{p}'" for p in partitioning) + "]")
    return f"CREATE TABLE {prefix}.{table} ({body})" + (f" WITH ({', '.join(props)})" if props else "")


def create_view_sql(prefix: str, view: str) -> str:
    return f"CREATE OR REPLACE VIEW {prefix}.{view} AS" + VIEWS[view].format(t=prefix)


def literal(value: str, kind: str) -> str:
    if value == "":
        return "NULL"
    if kind == "VARCHAR":
        return "'" + value.replace("'", "''") + "'"
    if kind == "DATE":
        return f"DATE '{value}'"
    if kind.startswith("TIMESTAMP"):
        return f"TIMESTAMP '{value}'"
    return value

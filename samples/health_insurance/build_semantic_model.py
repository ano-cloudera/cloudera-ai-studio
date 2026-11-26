#!/usr/bin/env python3
"""Create, validate and publish the health insurance semantic model through the Backend API.

Run it after load_health_insurance.py, once the Trino Data Source exists in Data Sources:

    HI_TRINO_CATALOG=iceberg HI_TRINO_SCHEMA=demo_asuransi python3 samples/health_insurance/build_semantic_model.py
    ... --dry-run      print what it would create, call nothing
    ... --no-publish   create and validate the draft, leave publishing to the Semantic Layer page
    ... --base-url URL the Backend URL with its secret path (inside a Cloudera AI Session it is derived)

The catalog and schema must be the ones the data was loaded into: they are required, never assumed. Every run adds a new version of
the model, so it is safe to run again. The machinery is scripts/semantic_api.py.
"""
from __future__ import annotations

import csv
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "scripts"))
import semantic_api  # noqa: E402


def provider_places() -> dict[str, list[float]]:
    """Where each provider is (from the generated data), so a result by provider is drawn on the map."""
    path = HERE / "data" / "penyedia.csv"
    if not path.exists():
        sys.path.insert(0, str(HERE))
        import generate_data  # noqa: PLC0415

        generate_data.main([])
    with path.open(newline="", encoding="utf-8") as fh:
        return {r["nama_penyedia"]: [float(r["latitude"]), float(r["longitude"])] for r in csv.DictReader(fh)}


_ALERTED = "id_alert IS NOT NULL"
_CLOSED = "status_investigasi IN ('Terbukti fraud', 'Bukan fraud')"
_DECIDED = "status_klaim <> 'Diproses'"

SPEC = {
    "key": "asuransi_kesehatan", "name": "Klaim Asuransi Kesehatan", "catalog": "", "schema": "",
    "description": "Klaim asuransi kesehatan swasta: tagihan dan pembayaran per penyedia, dokter, diagnosis dan produk, alert fraud dari model "
                   "skoring dan hasil investigasinya, serta rasio klaim terhadap premi. Data contoh (sintetis).",
    # What an overview starts with: how much of the claims carries a fraud alert, how often, the loss proven, and the claim ratio.
    "headline": ["nilai_klaim_beralert", "tingkat_alert", "kerugian_fraud_terbukti", "rasio_klaim"],
    "home": {
        "nilai_klaim_beralert": {"better": "down"},
        "tingkat_alert": {"better": "down", "target": 2},
        "kerugian_fraud_terbukti": {"better": "down"},
        "rasio_klaim": {"better": "down", "target": 75},
    },
    "geo": {"penyedia": {}},  # filled in main()
    "entities": [
        {"key": "klaim", "name": "Klaim", "table": "v_hi_klaim", "kind": "view", "primary_key": "id_klaim",
         "description": "Satu baris per klaim asuransi kesehatan: peserta, penyedia (rumah sakit atau klinik), dokter, tanggal, jenis layanan, "
                        "diagnosis, lama rawat, tagihan, nilai disetujui dan dibayar, metode (Cashless atau Reimbursement) dan status. Dilengkapi "
                        "tanda keterkaitan (rekening dan telepon yang dipakai bersama, klaim ganda, rawat ulang) dan alert fraud beserta hasil "
                        "investigasinya."},
        {"key": "rasio_klaim_premi", "name": "Rasio klaim terhadap premi", "table": "v_hi_rasio_klaim", "kind": "view",
         "primary_key": "bulan,produk",
         "description": "Premi diperoleh dan klaim dibayar per bulan dan produk. Dipakai untuk rasio klaim (loss ratio)."},
    ],
    # (key, name, entity, column, data type, synonyms, description)
    "dimensions": [
        ("tanggal_masuk", "Tanggal Masuk", "klaim", "tanggal_masuk", "Date", ["tanggal", "tanggal kunjungan", "tanggal layanan", "bulan", "periode"],
         "Tanggal peserta berkunjung atau masuk rawat inap."),
        ("jenis_layanan", "Jenis Layanan", "klaim", "jenis_layanan", "String", ["layanan", "igd"],
         "Rawat Jalan, Rawat Inap, atau Gawat Darurat."),
        ("diagnosis", "Diagnosis", "klaim", "nama_diagnosis", "String", ["penyakit", "nama diagnosis", "diagnosa"],
         "Diagnosis utama klaim, misalnya Demam berdarah dengue, Pneumonia, Apendisitis akut."),
        ("kode_diagnosis", "Kode Diagnosis", "klaim", "kode_diagnosis", "String", ["kode icd", "icd-10", "kode penyakit"],
         "Kode ICD-10 diagnosis utama (subset diagnosis umum)."),
        ("kelompok_diagnosis", "Kelompok Diagnosis", "klaim", "kelompok_diagnosis", "String", ["kategori penyakit", "kelompok penyakit"],
         "Infeksi, Pernapasan, Kardiovaskular, Metabolik, Pencernaan, Bedah, Kehamilan, dan lainnya."),
        ("tindakan_utama", "Tindakan Utama", "klaim", "tindakan_utama", "String", ["tindakan", "prosedur", "operasi"],
         "Tindakan utama, misalnya Apendektomi, Seksio sesarea, Hemodialisis, Konsultasi dan pengobatan."),
        ("metode_klaim", "Metode Klaim", "klaim", "metode_klaim", "String", ["cashless", "reimbursement", "penggantian biaya", "metode"],
         "Cashless (ditagihkan penyedia rekanan) atau Reimbursement (peserta membayar dulu lalu diganti ke rekeningnya)."),
        ("status_klaim", "Status Klaim", "klaim", "status_klaim", "String", ["status pembayaran klaim", "keputusan klaim"],
         "Dibayar, Ditolak, atau Diproses (belum diputuskan)."),
        ("alasan_penolakan", "Alasan Penolakan", "klaim", "alasan_penolakan", "String", ["alasan ditolak", "penyebab penolakan"],
         "Untuk klaim yang ditolak: Dokumen tidak lengkap, Masa tunggu belum terpenuhi, Melebihi limit tahunan, Di luar pertanggungan."),
        ("penyedia", "Penyedia", "klaim", "nama_penyedia", "String", ["rumah sakit", "rs", "klinik", "fasilitas kesehatan", "faskes", "provider", "nama rumah sakit", "nama klinik"],
         "Nama rumah sakit atau klinik yang melayani: dimensi untuk pertanyaan rumah sakit mana, klinik mana, penyedia mana. Semua nama fiktif (RS Demo ..., Klinik Demo ...)."),
        ("tipe_penyedia", "Tipe Penyedia", "klaim", "tipe_penyedia", "String", ["jenis penyedia", "rumah sakit atau klinik"],
         "Rumah Sakit atau Klinik."),
        ("kelas_penyedia", "Kelas Penyedia", "klaim", "kelas_penyedia", "String", ["kelas rumah sakit", "kelas rs", "tipe kelas"],
         "Kelas penyedia: Kelas A, Kelas B, Kelas C, Kelas D (rumah sakit), Klinik Utama, Klinik Pratama. Ini kelasnya, bukan nama penyedia."),
        ("status_rekanan", "Status Rekanan", "klaim", "status_rekanan", "String", ["rekanan", "non-rekanan", "jaringan provider"],
         "Rekanan (bekerja sama, bisa cashless) atau Non-rekanan."),
        ("provinsi", "Provinsi", "klaim", "provinsi", "String", ["wilayah", "daerah", "peta", "lokasi"],
         "Provinsi tempat penyedia berada."),
        ("kota", "Kota", "klaim", "kota", "String", ["kabupaten", "kota penyedia"], "Kota tempat penyedia berada."),
        ("dokter", "Dokter", "klaim", "kode_dokter", "String", ["kode dokter", "dokter penanggung jawab", "dpjp"],
         "Kode dokter yang menangani (dokter ditulis sebagai kode, bukan nama)."),
        ("spesialisasi", "Spesialisasi Dokter", "klaim", "spesialisasi", "String", ["spesialis", "keahlian dokter"],
         "Umum atau spesialis, misalnya Sp.PD (Penyakit Dalam), Sp.A (Anak), Sp.B (Bedah)."),
        ("produk", "Produk", "klaim", "produk", "String", ["plan", "produk asuransi", "paket"],
         "Sehat Silver, Sehat Gold, Sehat Platinum (individu), Kumpulan Standar, Kumpulan Eksekutif (korporat)."),
        ("segmen", "Segmen", "klaim", "segmen", "String", ["individu", "korporat", "kumpulan"], "Individu atau Korporat."),
        ("kelompok_usia", "Kelompok Usia", "klaim", "kelompok_usia", "String", ["usia", "umur"], "0-17, 18-30, 31-45, 46-60, 60+."),
        ("peserta", "Peserta", "klaim", "id_peserta", "String", ["id peserta", "nomor peserta", "tertanggung", "nasabah"],
         "Nomor peserta (tertanggung) yang mengajukan klaim."),
        ("rekening_penggantian", "Rekening Penggantian", "klaim", "rekening_penggantian_hash", "String",
         ["rekening", "nomor rekening", "rekening tujuan", "rekening pencairan"],
         "Rekening tujuan penggantian biaya (Reimbursement), disamarkan (REK-...). Kosong untuk klaim Cashless."),
        ("rekening_dipakai_bersama", "Rekening Dipakai Bersama", "klaim", "rekening_dipakai_bersama", "String",
         ["rekening bersama", "rekening yang sama", "satu rekening banyak peserta"],
         "Rekening dipakai bersama (rekening penggantian klaim ini menerima penggantian untuk 3 peserta atau lebih, tanda jaringan), Rekening sendiri, atau Tanpa rekening (Cashless)."),
        ("telepon_dipakai_bersama", "Telepon Dipakai Bersama", "klaim", "telepon_dipakai_bersama", "String",
         ["telepon bersama", "nomor telepon yang sama"], "Telepon dipakai bersama (nomor telepon peserta dipakai 3 peserta atau lebih) atau Telepon sendiri."),
        ("klaim_ganda", "Klaim Ganda", "klaim", "klaim_ganda", "String", ["duplikat", "klaim duplikat", "kunjungan yang sama"],
         "Klaim ganda (kunjungan yang sama, yaitu peserta, tanggal dan diagnosis sama, diklaim di dua penyedia berbeda) atau Bukan klaim ganda."),
        ("rawat_ulang_7_hari", "Rawat Ulang 7 Hari", "klaim", "rawat_ulang_7_hari", "String", ["readmisi", "rawat ulang", "masuk lagi"],
         "Rawat ulang 7 hari (peserta masuk rawat inap lagi untuk diagnosis yang sama 0-7 hari setelah pulang) atau Bukan rawat ulang."),
        ("hari_kunjungan", "Hari Kunjungan", "klaim", "hari_kunjungan", "String", ["nama hari kunjungan"], "Senin sampai Minggu."),
        ("jenis_hari", "Hari Kerja atau Akhir Pekan", "klaim", "jenis_hari", "String", ["akhir pekan", "weekend", "hari kerja"],
         "Hari kerja atau Akhir pekan."),
        ("waktu_kunjungan", "Waktu Kunjungan", "klaim", "waktu_kunjungan", "String", ["jam kunjungan", "siang atau malam"],
         "Siang (06.00-17.59) atau Malam (18.00-05.59)."),
        ("tingkat_risiko", "Tingkat Risiko", "klaim", "tingkat_risiko", "String", ["risiko fraud", "level risiko"],
         "Tingkat risiko dari model skoring: Tinggi, Sedang, atau Tidak ada alert."),
        ("status_investigasi", "Status Investigasi", "klaim", "status_investigasi", "String",
         ["hasil investigasi", "terbukti fraud", "bukan fraud", "sedang diperiksa"],
         "Hasil terakhir pemeriksaan alert: Terbukti fraud, Bukan fraud, Sedang diperiksa, Belum diperiksa, atau Tidak ada alert."),
        ("alasan_alert", "Alasan Alert", "klaim", "alasan_alert", "String", ["alasan utama", "penyebab alert", "kenapa ditandai"],
         "Alasan utama model menandai klaim, misalnya rekening dipakai banyak peserta atau dokter dengan jumlah klaim tidak wajar."),
        ("bulan_premi", "Bulan Premi", "rasio_klaim_premi", "bulan", "Date", [], "Bulan premi diperoleh."),
        ("produk_premi", "Produk (Premi)", "rasio_klaim_premi", "produk", "String", [], "Produk asuransi."),
        ("segmen_premi", "Segmen (Premi)", "rasio_klaim_premi", "segmen", "String", [], "Individu atau Korporat."),
    ],
    # (key, name, entity, expression, unit, synonyms, business definition)
    "metrics": [
        ("jumlah_klaim", "Jumlah Klaim", "klaim", "COUNT(*)", "klaim", ["banyak klaim", "volume klaim", "total klaim", "berapa klaim"],
         "Jumlah klaim yang diajukan."),
        ("total_tagihan", "Total Tagihan (IDR)", "klaim", "SUM(jumlah_tagihan_idr)", "IDR", ["tagihan", "nilai tagihan", "billing"],
         "Jumlah yang ditagihkan penyedia atau peserta, sebelum diputuskan."),
        ("total_dibayar", "Total Klaim Dibayar (IDR)", "klaim", "SUM(jumlah_dibayar_idr)", "IDR",
         ["klaim dibayar", "pembayaran klaim", "nilai klaim dibayar", "biaya klaim", "beban klaim"],
         "Jumlah klaim yang sudah dibayar. Klaim ditolak dan yang masih diproses bernilai nol."),
        ("rata_tagihan", "Rata-rata Tagihan per Klaim (IDR)", "klaim", "AVG(jumlah_tagihan_idr)", "IDR",
         ["biaya rata-rata", "rata-rata biaya per kasus", "biaya per kasus", "rata-rata tagihan"],
         "Rata-rata tagihan per klaim. Bandingkan antar penyedia sekelas dan untuk diagnosis yang sama."),
        ("rata_lama_rawat", "Rata-rata Lama Rawat (hari)", "klaim", "AVG(CASE WHEN jenis_layanan = 'Rawat Inap' THEN lama_rawat_hari END)", "hari",
         ["lama rawat", "length of stay", "los", "lama dirawat"], "Rata-rata hari rawat inap per klaim rawat inap."),
        ("jumlah_peserta", "Jumlah Peserta", "klaim", "COUNT(DISTINCT id_peserta)", "peserta",
         ["peserta berbeda", "berapa peserta", "tertanggung berbeda"],
         "Jumlah peserta berbeda yang mengajukan klaim. Dipecah per rekening penggantian, menunjukkan berapa peserta memakai rekening yang sama."),
        ("tingkat_penolakan", "Tingkat Penolakan Klaim (%)", "klaim",
         f"COUNT(CASE WHEN status_klaim = 'Ditolak' THEN 1 END) * 100.0 / NULLIF(COUNT(CASE WHEN {_DECIDED} THEN 1 END), 0)", "percent",
         ["persentase ditolak", "rasio penolakan", "klaim ditolak"], "Klaim ditolak dibagi klaim yang sudah diputuskan."),
        ("rata_hari_keputusan", "Rata-rata Waktu Keputusan (hari)", "klaim", "AVG(hari_sampai_keputusan)", "hari",
         ["waktu proses klaim", "lama proses", "turnaround time", "sla klaim"], "Rata-rata hari dari pengajuan sampai keputusan klaim."),
        ("klaim_per_hari_praktik", "Rata-rata Klaim per Hari Praktik", "klaim", "COUNT(*) * 1.0 / NULLIF(COUNT(DISTINCT tanggal_masuk), 0)", "klaim",
         ["klaim per hari", "pasien per hari", "kunjungan per hari"],
         "Jumlah klaim dibagi jumlah hari yang punya klaim. Dipecah per dokter, menunjukkan berapa pasien kita yang ditangani dokter itu dalam sehari."),
        ("jumlah_klaim_beralert", "Jumlah Klaim Ber-alert", "klaim", f"COUNT(CASE WHEN {_ALERTED} THEN 1 END)", "klaim",
         ["klaim ditandai", "klaim mencurigakan", "klaim bertanda fraud", "klaim yang ditandai alert"], "Jumlah klaim yang ditandai alert oleh model skoring fraud."),
        ("nilai_klaim_beralert", "Nilai Klaim Ber-alert (IDR)", "klaim", f"SUM(CASE WHEN {_ALERTED} THEN jumlah_tagihan_idr END)", "IDR",
         ["nilai alert", "nilai klaim mencurigakan", "nilai klaim ditandai", "nilai klaim yang ditandai alert", "eksposur fraud"],
         "Total tagihan klaim yang ditandai alert fraud."),
        ("tingkat_alert", "Tingkat Alert (%)", "klaim", f"COUNT(CASE WHEN {_ALERTED} THEN 1 END) * 100.0 / NULLIF(COUNT(*), 0)", "percent",
         ["persentase alert", "proporsi klaim ditandai", "alert rate"], "Persentase klaim yang ditandai alert fraud dari semua klaim."),
        ("kerugian_fraud_terbukti", "Kerugian Fraud Terbukti (IDR)", "klaim",
         "SUM(CASE WHEN status_investigasi = 'Terbukti fraud' THEN jumlah_dibayar_idr END)", "IDR",
         ["kerugian fraud", "kerugian", "fraud terbukti", "uang hilang"], "Klaim yang sudah dibayar lalu terbukti fraud dalam investigasi."),
        ("potensi_kerugian", "Potensi Kerugian Belum Diputus (IDR)", "klaim",
         "SUM(CASE WHEN tingkat_risiko = 'Tinggi' AND status_investigasi IN ('Belum diperiksa', 'Sedang diperiksa') THEN jumlah_tagihan_idr END)", "IDR",
         ["potensi kerugian", "eksposur terbuka", "risiko belum diperiksa"],
         "Tagihan klaim berisiko Tinggi yang investigasinya belum selesai."),
        ("tingkat_rawat_ulang", "Tingkat Rawat Ulang 7 Hari (%)", "klaim",
         "COUNT(CASE WHEN rawat_ulang_7_hari = 'Rawat ulang 7 hari' THEN 1 END) * 100.0 / NULLIF(COUNT(CASE WHEN jenis_layanan = 'Rawat Inap' THEN 1 END), 0)", "percent",
         ["readmission rate", "tingkat readmisi", "persentase rawat ulang"], "Rawat inap ulang dalam 7 hari dibagi semua rawat inap."),
        ("tingkat_alert_terbukti", "Tingkat Alert Terbukti (%)", "klaim",
         f"COUNT(CASE WHEN status_investigasi = 'Terbukti fraud' THEN 1 END) * 100.0 / NULLIF(COUNT(CASE WHEN {_CLOSED} THEN 1 END), 0)", "percent",
         ["presisi model", "ketepatan alert", "akurasi alert", "persentase alert terbukti fraud", "persen alert yang terbukti"],
         "Dari alert yang investigasinya selesai, persentase yang terbukti fraud."),
        ("rasio_klaim", "Rasio Klaim (%)", "rasio_klaim_premi", "SUM(klaim_dibayar_idr) * 100.0 / NULLIF(SUM(premi_idr), 0)", "percent",
         ["loss ratio", "claim ratio", "rasio klaim terhadap premi"], "Klaim dibayar dibagi premi diperoleh. Di atas 100 persen berarti klaim melebihi premi."),
        ("total_premi", "Total Premi (IDR)", "rasio_klaim_premi", "SUM(premi_idr)", "IDR", ["premi", "premi diperoleh", "pendapatan premi"],
         "Premi diperoleh pada periode yang dipilih."),
    ],
    # (key, term, definition, related metric keys). Terms are not tied to metrics: a word in many questions would pull the wrong metric.
    "terms": [
        ("upcoding", "Upcoding", "Menagih diagnosis atau tindakan yang lebih berat atau lebih mahal dari yang sebenarnya. Terlihat dari tagihan "
                                 "penyedia yang jauh di atas penyedia sekelas untuk diagnosis yang sama.", []),
        ("klaim_ganda", "Klaim ganda", "Kunjungan yang sama (peserta, tanggal dan diagnosis sama) diklaim di dua penyedia berbeda.", []),
        ("rawat_ulang", "Rawat ulang", "Peserta masuk rawat inap lagi untuk diagnosis yang sama tidak lama setelah pulang (di sini 0-7 hari).", []),
        ("cashless", "Cashless dan Reimbursement", "Cashless: penyedia rekanan menagih langsung ke asuransi. Reimbursement: peserta membayar dulu, "
                                                   "lalu biaya diganti ke rekening peserta.", []),
        ("jaringan_fraud", "Fraud berjaringan", "Sekelompok peserta, penyedia atau dokter yang bekerja sama. Tiap klaim tampak wajar; polanya terlihat "
                                                "dari keterkaitan, misalnya banyak peserta memakai satu rekening atau satu nomor telepon.", []),
        ("alert_fraud", "Alert fraud", "Penanda dari model skoring untuk klaim yang perlu diperiksa, dengan skor 0 sampai 1 dan alasan utama. "
                                       "Model di sini adalah model contoh yang dilatih dari data sintetis.", []),
        ("rasio_klaim_term", "Rasio klaim (loss ratio)", "Klaim dibayar dibagi premi diperoleh, dalam persen.", []),
        ("dbd", "DBD", "Demam berdarah dengue. Klaimnya naik setiap musim hujan; lonjakan yang tersebar di banyak penyedia adalah wabah, "
                       "bukan fraud.", []),
    ],
}


def main(argv: list[str] | None = None) -> int:
    catalog, schema = os.getenv("HI_TRINO_CATALOG"), os.getenv("HI_TRINO_SCHEMA")
    if not catalog or not schema:
        print("Set HI_TRINO_CATALOG and HI_TRINO_SCHEMA to where load_health_insurance.py put the data. Nothing was created.", file=sys.stderr)
        return 2
    SPEC["catalog"], SPEC["schema"] = catalog, schema
    SPEC["geo"] = {"penyedia": provider_places()}
    return semantic_api.main(SPEC, argv, doc=__doc__)


if __name__ == "__main__":
    raise SystemExit(main())

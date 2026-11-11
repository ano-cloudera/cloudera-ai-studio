#!/usr/bin/env python3
"""Create, validate and publish the fuel distribution semantic model through the Backend API.

Run it in a Session terminal of the Cloudera AI project, after the tables are in Trino and the Trino Data Source exists:

    python3 samples/fuel_distribution/build_semantic_model.py            # create a new version, validate, publish to Ask Data
    python3 samples/fuel_distribution/build_semantic_model.py --dry-run  # print what it would create, call nothing
    python3 samples/fuel_distribution/build_semantic_model.py --no-publish

Every run adds a new version of the model, so it is safe to run again. The machinery is scripts/semantic_api.py.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import semantic_api  # noqa: E402

_LATE = "COUNT(CASE WHEN status_pengiriman = 'Terlambat' THEN 1 END)"
_FINISHED = "NULLIF(COUNT(CASE WHEN status_pengiriman <> 'Dalam_Perjalanan' THEN 1 END), 0)"

SPEC = {
    "key": "fuel_distribution", "name": "Distribusi BBM", "catalog": "iceberg", "schema": "default",
    "description": "Penyaluran BBM dari terminal ke SPBU dan pelanggan industri: volume, ketepatan pengiriman, dan realisasi BBM subsidi terhadap kuota.",
    "entities": [
        {"key": "penyaluran", "name": "Penyaluran (Loading Order)", "table": "fuel_deliveries", "kind": "table", "primary_key": "id_lo",
         "description": "Satu baris per Loading Order (LO): pengiriman BBM dari terminal ke SPBU atau pelanggan industri, dengan produk, volume dalam KL, nilai, jarak, durasi, SLA, dan status. Dipakai untuk volume, nilai, ketepatan dan keterlambatan pengiriman."},
        {"key": "kuota_subsidi", "name": "Kuota BBM subsidi", "table": "v_fuel_quota_attainment", "kind": "view", "primary_key": "regional,produk,bulan",
         "description": "Kuota bulanan BBM subsidi (Pertalite dan Biosolar) per regional dan produk, dengan realisasi penyaluran ritel di bulan yang sama. Dipakai untuk pencapaian dan sisa kuota."},
        {"key": "pelanggan", "name": "Pelanggan (SPBU dan industri)", "table": "fuel_customers", "kind": "table", "primary_key": "kode_pelanggan",
         "description": "Satu baris per SPBU atau pelanggan industri, dengan tipe, regional, provinsi dan terminal asalnya. Dipakai untuk menghitung jumlah SPBU dan pelanggan."},
    ],
    # (key, name, entity, column, data type, synonyms, description)
    "dimensions": [
        ("tanggal_transaksi", "Tanggal Transaksi", "penyaluran", "tanggal_transaksi", "Date", ["tanggal", "bulan", "periode", "tahun", "month", "date"], "Tanggal Loading Order dibuat dan dikirim."),
        ("regional", "Regional", "penyaluran", "regional", "String", ["wilayah pemasaran", "region", "wilayah regional"], "Wilayah pemasaran Pertamina: Sumbagut, Sumbagsel, Jawa Bagian Barat, Jawa Bagian Tengah, Jatimbalinus, Kalimantan, Sulawesi, Papua Maluku."),
        ("provinsi", "Provinsi", "penyaluran", "provinsi", "String", ["province", "wilayah", "daerah", "peta"], "Provinsi tujuan pengiriman (lokasi SPBU atau pelanggan)."),
        ("fuel_terminal", "Terminal (TBBM)", "penyaluran", "fuel_terminal", "String", ["terminal", "tbbm", "depot", "fuel terminal", "terminal bbm"], "Terminal BBM asal pasokan. Bisa berbeda dari terminal asal pelanggan bila terminal utamanya sedang tidak beroperasi."),
        ("segmen_bisnis", "Segmen Bisnis", "penyaluran", "segmen_bisnis", "String", ["segmen", "ritel", "industri", "b2b", "ritel atau industri"], "Ritel_SPBU untuk penyaluran ke SPBU, Industri_B2B untuk pelanggan industri."),
        ("kode_pelanggan", "Kode Pelanggan (SPBU)", "penyaluran", "kode_pelanggan", "String", ["spbu", "kode spbu", "pelanggan", "nomor spbu", "kode pelanggan"], "Kode SPBU atau pelanggan industri penerima pasokan."),
        ("tipe_pelanggan", "Tipe Pelanggan", "penyaluran", "nama_tipe_pelanggan", "String", ["tipe spbu", "jenis spbu", "coco", "codo", "dodo", "sektor industri", "kepemilikan spbu"], "SPBU_COCO, SPBU_CODO atau SPBU_DODO untuk ritel, dan Industri_<sektor> untuk pelanggan industri."),
        ("produk", "Produk", "penyaluran", "produk", "String", ["jenis bbm", "bbm", "fuel", "jenis produk", "pertalite", "biosolar", "pertamax"], "Produk BBM yang dikirim: Pertalite, Biosolar, Pertamax, Pertamax Turbo, Dexlite, Pertamina Dex, Solar Industri, MFO 180 cSt, Pertamax Industri, Avtur."),
        ("kategori_bbm", "Kategori BBM", "penyaluran", "kategori_bbm", "String", ["subsidi", "non subsidi", "kategori", "bbm subsidi"], "Subsidi atau Non-Subsidi."),
        ("status_pengiriman", "Status Pengiriman", "penyaluran", "status_pengiriman", "String", ["status", "terlambat", "terkirim", "tepat waktu"], "Terkirim (tepat waktu), Terlambat (durasi melebihi SLA), atau Dalam_Perjalanan (belum selesai)."),
        ("mobil_tangki", "Mobil Tangki", "penyaluran", "nopol_mobil_tangki", "String", ["truk", "armada", "nopol", "plat nomor", "truk tangki"], "Nomor polisi mobil tangki yang mengirim."),
        ("kuota_regional", "Regional (Kuota)", "kuota_subsidi", "regional", "String", ["wilayah kuota", "regional kuota"], "Regional pemilik kuota BBM subsidi."),
        ("kuota_produk", "Produk Subsidi", "kuota_subsidi", "produk", "String", ["produk kuota", "bbm subsidi", "pertalite", "biosolar"], "Produk subsidi yang dikuotakan: Pertalite atau Biosolar."),
        ("kuota_bulan", "Bulan Kuota", "kuota_subsidi", "bulan", "Date", ["bulan", "periode kuota", "tanggal"], "Bulan berlakunya kuota (tanggal 1 setiap bulan)."),
        ("pelanggan_regional", "Regional (Pelanggan)", "pelanggan", "regional", "String", ["regional pelanggan"], "Regional tempat SPBU atau pelanggan berada."),
        ("pelanggan_provinsi", "Provinsi (Pelanggan)", "pelanggan", "provinsi", "String", ["provinsi pelanggan", "provinsi spbu"], "Provinsi lokasi SPBU atau pelanggan."),
        ("pelanggan_tipe", "Tipe (Pelanggan)", "pelanggan", "nama_tipe_pelanggan", "String", ["tipe spbu pelanggan", "jenis pelanggan"], "Tipe SPBU (COCO, CODO, DODO) atau sektor industri."),
        ("pelanggan_terminal", "Terminal Asal (Pelanggan)", "pelanggan", "fuel_terminal", "String", ["terminal asal", "terminal pelanggan"], "Terminal yang biasanya memasok pelanggan ini."),
    ],
    # (key, name, entity, expression, unit, synonyms, business definition)
    "metrics": [
        ("total_volume", "Total Volume (KL)", "penyaluran", "SUM(volume_kl)", "KL", ["volume", "volume penyaluran", "penyaluran", "total penyaluran", "kiloliter", "throughput", "jumlah penyaluran"], "Total BBM yang disalurkan, dalam kiloliter (KL)."),
        ("total_nilai", "Total Nilai Penyaluran (IDR)", "penyaluran", "SUM(total_nilai_idr)", "IDR", ["nilai penyaluran", "nilai penjualan", "omzet", "revenue", "nilai transaksi", "pendapatan penyaluran"], "Total nilai penyaluran dalam rupiah (volume dikali harga per liter)."),
        ("jumlah_lo", "Jumlah LO", "penyaluran", "COUNT(id_lo)", "LO", ["loading order", "jumlah pengiriman", "jumlah loading order", "jumlah lo", "number of deliveries"], "Jumlah Loading Order (satu LO adalah satu pengiriman mobil tangki)."),
        ("tingkat_keterlambatan", "Tingkat Keterlambatan (%)", "penyaluran", f"{_LATE} * 100.0 / {_FINISHED}", "percent",
         ["keterlambatan", "tingkat keterlambatan", "persentase keterlambatan", "persentase terlambat", "late rate", "delay rate", "telat", "pengiriman terlambat"], "Persentase LO yang terlambat dari semua LO yang sudah selesai (yang masih dalam perjalanan tidak dihitung). Terlambat berarti durasi melebihi SLA."),
        ("ketepatan_pengiriman", "Ketepatan Pengiriman (%)", "penyaluran", f"COUNT(CASE WHEN status_pengiriman = 'Terkirim' THEN 1 END) * 100.0 / {_FINISHED}", "percent",
         ["ketepatan waktu", "on time delivery", "ketepatan pengiriman", "tepat waktu", "on-time rate"], "Persentase LO yang tiba dalam batas SLA, dari semua LO yang sudah selesai."),
        ("jumlah_terlambat", "Jumlah LO Terlambat", "penyaluran", _LATE, "LO", ["lo terlambat", "jumlah keterlambatan", "jumlah pengiriman terlambat"], "Jumlah LO dengan durasi pengiriman melebihi SLA."),
        ("rata_durasi", "Rata-rata Durasi Pengiriman (menit)", "penyaluran", "AVG(durasi_kirim_menit)", "minutes", ["durasi pengiriman", "lama pengiriman", "waktu tempuh", "delivery duration", "durasi kirim"], "Rata-rata durasi dari berangkat sampai bongkar, dalam menit, untuk LO yang sudah selesai."),
        ("rata_jarak", "Rata-rata Jarak Tempuh (km)", "penyaluran", "AVG(jarak_tempuh_km)", "km", ["jarak tempuh", "jarak pengiriman", "distance", "jarak"], "Rata-rata jarak dari terminal ke tujuan, dalam kilometer."),
        ("rata_menit_terlambat", "Rata-rata Menit Keterlambatan", "penyaluran", "AVG(CASE WHEN status_pengiriman = 'Terlambat' THEN durasi_kirim_menit - sla_menit END)", "minutes", ["lama keterlambatan", "rata-rata keterlambatan", "delay minutes", "berapa lama telat"], "Rata-rata menit melebihi SLA, hanya untuk LO yang terlambat."),
        ("volume_subsidi", "Volume BBM Subsidi (KL)", "penyaluran", "SUM(CASE WHEN kategori_bbm = 'Subsidi' THEN volume_kl END)", "KL", ["volume subsidi", "penyaluran subsidi", "bbm subsidi", "volume bbm subsidi"], "Volume BBM subsidi (Pertalite dan Biosolar) yang disalurkan, dalam KL."),
        ("porsi_subsidi", "Porsi BBM Subsidi (%)", "penyaluran", "SUM(CASE WHEN kategori_bbm = 'Subsidi' THEN volume_kl END) * 100.0 / SUM(volume_kl)", "percent", ["porsi subsidi", "persentase subsidi", "subsidi share", "proporsi subsidi", "share subsidi"], "BBM subsidi sebagai persentase dari total volume."),
        ("rata_volume_lo", "Rata-rata Volume per LO (KL)", "penyaluran", "AVG(volume_kl)", "KL", ["volume per lo", "rata-rata volume", "ukuran pengiriman"], "Rata-rata KL per Loading Order."),
        ("harga_rata", "Harga Rata-rata per Liter (IDR)", "penyaluran", "SUM(total_nilai_idr) / (SUM(volume_kl) * 1000.0)", "IDR", ["harga per liter", "harga rata-rata", "average price", "harga bbm"], "Nilai total dibagi total liter yang disalurkan."),
        ("spbu_aktif", "Jumlah SPBU Aktif", "penyaluran", "COUNT(DISTINCT CASE WHEN segmen_bisnis = 'Ritel_SPBU' THEN kode_pelanggan END)", "stations", ["spbu aktif", "spbu yang menerima pasokan", "active stations", "spbu yang dikirimi"], "Jumlah SPBU berbeda yang menerima pengiriman pada periode yang dipilih."),
        ("truk_aktif", "Jumlah Mobil Tangki Aktif", "penyaluran", "COUNT(DISTINCT nopol_mobil_tangki)", "trucks", ["armada aktif", "jumlah truk", "jumlah mobil tangki", "truk aktif"], "Jumlah mobil tangki berbeda yang melakukan pengiriman."),
        ("total_kuota", "Total Kuota BBM Subsidi (KL)", "kuota_subsidi", "SUM(kuota_kl)", "KL", ["kuota", "kuota subsidi", "alokasi", "kuota bbm", "total kuota"], "Total kuota BBM subsidi dalam KL pada periode yang dipilih."),
        ("realisasi_subsidi", "Realisasi BBM Subsidi (KL)", "kuota_subsidi", "SUM(realisasi_kl)", "KL", ["realisasi", "realisasi subsidi", "realisasi penyaluran subsidi", "realisasi bbm"], "Volume BBM subsidi yang benar-benar disalurkan ke SPBU, dalam KL."),
        ("pencapaian_kuota", "Pencapaian Kuota (%)", "kuota_subsidi", "SUM(realisasi_kl) * 100.0 / NULLIF(SUM(kuota_kl), 0)", "percent",
         ["pencapaian kuota", "realisasi terhadap kuota", "realisasi vs kuota", "realisasi dibanding kuota", "serapan kuota", "quota attainment", "kuota terpakai"], "Realisasi dibagi kuota. Di atas 100 persen berarti kuota terlampaui."),
        ("sisa_kuota", "Sisa Kuota (KL)", "kuota_subsidi", "SUM(kuota_kl) - SUM(realisasi_kl)", "KL", ["sisa kuota", "kuota tersisa", "remaining quota", "kuota yang belum terpakai"], "Kuota dikurangi realisasi. Negatif berarti kuota sudah terlampaui."),
        ("jumlah_spbu", "Jumlah SPBU", "pelanggan", "COUNT(CASE WHEN segmen_bisnis = 'Ritel_SPBU' THEN kode_pelanggan END)", "stations", ["total spbu", "berapa spbu", "number of stations", "jumlah spbu kita"], "Jumlah SPBU yang terdaftar sebagai pelanggan."),
        ("jumlah_industri", "Jumlah Pelanggan Industri", "pelanggan", "COUNT(CASE WHEN segmen_bisnis = 'Industri_B2B' THEN kode_pelanggan END)", "customers", ["pelanggan b2b", "jumlah industri", "industrial customers", "pelanggan industri"], "Jumlah pelanggan industri (B2B) yang terdaftar."),
    ],
    # (key, term, definition, related metric keys). A term is left unrelated to any metric on purpose: a phrase such as "BBM subsidi" or
    # "fuel terminal" appears in many questions, and tying it to metrics made the resolver pick the wrong one for the quota questions.
    "terms": [
        ("lo", "LO (Loading Order)", "Perintah muat dari terminal ke satu SPBU atau pelanggan. Satu LO adalah satu pengiriman mobil tangki.", []),
        ("tbbm", "TBBM / Fuel Terminal", "Terminal BBM tempat BBM disimpan dan dimuat ke mobil tangki sebelum dikirim.", []),
        ("coco_codo_dodo", "COCO, CODO, DODO", "Kepemilikan SPBU: COCO milik dan dioperasikan perusahaan, CODO milik perusahaan dan dioperasikan dealer, DODO milik dan dioperasikan dealer.", []),
        ("bbm_subsidi", "BBM subsidi", "Pertalite dan Biosolar dalam data ini. Penyalurannya dibatasi kuota per regional.", []),
        ("sla", "SLA pengiriman", "Batas waktu pengiriman satu LO: 60 menit ditambah waktu tempuh pada kecepatan 40 km per jam untuk jarak standar pelanggan. Melebihi SLA berarti Terlambat.", []),
        ("kuota", "Kuota BBM subsidi", "Batas volume bulanan BBM subsidi per regional dan produk. Pencapaian di atas 100 persen berarti kuota terlampaui.", []),
    ],
}


def main(argv: list[str] | None = None) -> int:
    return semantic_api.main(SPEC, argv, doc=__doc__)


if __name__ == "__main__":
    raise SystemExit(main())

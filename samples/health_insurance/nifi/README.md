# Aliran NiFi: klaim masuk, diberi skor, ditulis ke Iceberg

Aliran ini membuat demo "data bergerak": NiFi membuat klaim baru, API skoring menilainya, dan hasilnya ditulis ke Iceberg
(catalog yang sama dengan Trino). Beberapa detik kemudian klaim itu sudah terbaca di Trino dan ikut di jawaban Ask Data.

```
Generate Claim ──┐
                 ├─► Score Claim ─ Original ─► Write Claims to Iceberg   (hi_klaim_baru)
Generate Fraud ──┘        └ Response ─► Parse Alert ─► Route Alert ─► Extract Alert ─► Write Alerts to Iceberg  (hi_alert_baru)
```

| Processor | Fungsi |
|---|---|
| `Generate Claim` | Satu klaim rawat jalan biasa tiap 5 detik (peserta, penyedia, dokter, diagnosis dan tagihan acak) |
| `Generate Fraud Claim` | Satu klaim yang meniru jaringan rekening (peserta dan rekening dari jaringan, klinik dan dokter yang sama) tiap 30 detik |
| `Score Claim` | `POST /score` ke API skoring. Klaim aslinya keluar lewat `Original`, skornya lewat `Response` |
| `Parse Alert`, `Route Alert`, `Extract Alert` | Hanya jawaban yang membawa `alert` (skor 0,5 atau lebih) diteruskan, sebagai baris `hi_alert` |
| `Write Claims to Iceberg`, `Write Alerts to Iceberg` | `PutIceberg` ke `hi_klaim_baru` dan `hi_alert_baru` |
| `Log Write Failure` | Semua jalur gagal berakhir di sini, supaya kegagalan terlihat, bukan terbuang |

Hasil uji (data sintetis): klaim terbaca di Trino sekitar 5 detik setelah dibuat (median 4,8 detik; terlama 6,5 detik), klaim
fraud menghasilkan alert Tinggi dengan alasan berangka, dan klaim biasa tidak menghasilkan alert.

## Memasang di NiFi lain

1. Tabel dan view: `python samples/health_insurance/load_health_insurance.py` (membuat `hi_klaim_baru`, `hi_alert_baru`, dan view `*_gabungan`).
2. API skoring: Application CAI dari `scoring/service.py` (1 vCPU / 2 GiB, `SCORING_API_KEY` di environment-nya, tanpa SSO CAI karena dilindungi kunci Bearer).
3. Di NiFi: **Upload flow definition** (ikon process group di toolbar), pilih `flow/insurance_claims_demo.json`. File ini sengaja memuat
   penanda, bukan nilai asli. Isi:

| Di mana | Penanda | Isi dengan |
|---|---|---|
| Layanan `Kerberos Login` | `<workload-user>` dan sandi (kosong) | User dan sandi workload CDP yang boleh menulis ke tabel (IDBroker harus memetakan user itu ke Data Access Role) |
| Layanan `Hive Catalog` | `s3a://<datalake-bucket>/...` | Lokasi warehouse datalake yang sama dengan tabel di Trino |
| Processor `Score Claim`, `HTTP URL` | `<scoring-app-subdomain>.<cai-domain>` | Alamat Application skoring |
| Processor `Score Claim`, header `Authorization` | `Bearer <SCORING_API_KEY>` | Kunci Application skoring |

4. Aktifkan layanan (Controller Services), lalu **Start** kedua generator. Kedua generator berjalan di node utama saja, supaya
   klaimnya tidak berlipat sesuai jumlah node.

Syarat: `hadoop.security.authentication=kerberos` harus terbaca dari `/etc/hadoop/conf/core-site.xml` di node NiFi (keduanya ada di cluster
NiFi yang dipakai untuk menguji aliran ini; di cluster lain, cek dulu), dan `hive-site.xml` di `/etc/hive/conf/`.

## Menjalankan saat demo

- Nyalakan: Start `Generate Claim` dan `Generate Fraud Claim`. Matikan setelah selesai.
- Ukur latensi: `python samples/health_insurance/nifi/measure_latency.py --claims 10` (hanya membaca).
- Kembalikan angka dasar (mengosongkan `hi_klaim_baru` dan `hi_alert_baru`; riwayat tidak disentuh):
  `python samples/health_insurance/nifi/reset_stream.py --yes`. Lakukan ini sebelum menjalankan `judge_demo.json`, karena angka di sana
  untuk data tanpa klaim baru.
- Angka bergerak: tanyakan lewat Ask Data (cache jawaban bawaan `fallback` menjawab langsung dari data). Kartu di Home disimpan per
  versi semantic model, jadi tidak ikut bergerak.

## Yang perlu diketahui

- Kunci API skoring tertulis sebagai teks biasa di properti header `Authorization` pada `Score Claim` (NiFi tidak mengizinkan
  parameter sensitif di sana). Untuk data sintetis itu wajar, tetapi siapa pun yang bisa membuka konfigurasi processor bisa melihatnya.
- Sandi workload tersimpan terenkripsi di layanan `Kerberos Login`. Untuk penggunaan lain, ganti dengan keytab akun layanan.
- API skoring mengingat klaim yang ia nilai (agar klaim berikutnya dibandingkan dengan sebelumnya) hanya di memori. Saat Application
  dinyalakan ulang, ia mulai lagi dari riwayat.
- Skor berasal dari model contoh yang dilatih dari data sintetis: jangan disebut sebagai kemampuan deteksi fraud sungguhan.

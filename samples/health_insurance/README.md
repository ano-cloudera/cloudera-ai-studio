# Sample: fraud klaim asuransi kesehatan

Demo untuk asuransi kesehatan swasta: klaim dari rumah sakit dan klinik, alert dari model skoring fraud, hasil investigasi, dan
dokumen polis serta SOP. Ceritanya adalah **fraud berjaringan**: tiap klaim tampak wajar, polanya terlihat dari keterkaitan
(satu rekening dipakai banyak peserta, satu dokter dengan klaim mustahil banyak, satu rumah sakit yang selalu menagih lebih mahal).
Penutupnya membedakan wabah DBD yang wajar dari fraud.

Semua data sintetis dan semua nama fiktif ("RS Demo ...", dokter berupa kode). Model skoring adalah **model contoh** yang dilatih
dari data sintetis: jangan menyebut akurasinya sebagai kemampuan deteksi fraud sungguhan. Isi tabel, kolom dan pola: `KONTRAK-DATA.md`.

## Urutan menjalankan

Jalankan dari root repo di Session CAI (venv Backend). Kredensial Trino dibaca dari variabel `TRINO_HOST`, `TRINO_USER`,
`TRINO_PASSWORD` (dan `TRINO_PORT`, `TRINO_HTTP_SCHEME` bila bukan 443/https). Tujuan data **wajib** disebut:

```bash
export HI_TRINO_CATALOG=iceberg HI_TRINO_SCHEMA=demo_asuransi    # sesuaikan; schema khusus demo ini

# 1. Data (sekitar 10 detik). Deterministik: hasilnya selalu sama.
python samples/health_insurance/generate_data.py

# 2. Alert dan hasil investigasi dari model contoh (sekitar 10 detik). model.json sudah ada di repo.
python samples/health_insurance/scoring/score_history.py

# 3. Lihat dulu tujuannya (hanya membaca), lalu muat ke Iceberg lewat Trino (beberapa menit)
python samples/health_insurance/load_health_insurance.py --probe
python samples/health_insurance/load_health_insurance.py --create-schema

# 4. Pastikan semua pola terlihat di warehouse (gagal bila ada yang tidak muncul)
python samples/health_insurance/expected_answers.py

# 5. Buat Data Source Trino di aplikasi (Data Sources) yang menunjuk ke catalog dan schema yang sama, lalu pasang semantic model
python samples/health_insurance/build_semantic_model.py

# 6. Dokumen untuk Knowledge: unggah tiga PDF di samples/health_insurance/docs/ ke satu library (Knowledge -> New library)

# 7. Uji jawaban sebelum demo
python scripts/judge_answers.py --cases samples/health_insurance/judge_demo.json --out /home/cdsw/j_asuransi.json
```

Melatih ulang model (perlu scikit-learn, hanya bila data atau fitur diubah): `python samples/health_insurance/scoring/train.py`.

## Alur demo (sekitar 7 menit)

| # | Pertanyaan | Yang ditemukan |
|---|---|---|
| 1 | Berapa nilai klaim yang ditandai alert fraud pada Oktober 2026? | Besarnya masalah |
| 2 | Penyedia mana yang paling banyak klaim ber-alert? | RS Demo Kenanga Surabaya, lalu RS Demo Cendana Bekasi |
| 3 | Bandingkan rata-rata tagihan rawat inap antar rumah sakit kelas B | Cendana paling mahal (upcoding) |
| 4 | Dokter mana yang rata-rata klaim per hari praktiknya paling tinggi? | Satu dokter di Kenanga, sekitar 21 klaim per hari |
| 5 | Berapa total klaim dibayar ke rekening yang dipakai bersama? | Rp 916 juta |
| 6 | Klaim dengan rekening dipakai bersama terjadi di penyedia mana? | Satu klinik: Klinik Demo Melati |
| 6b | Untuk klaim reimbursement, rekening penggantian mana yang dipakai paling banyak peserta? | Enam rekening, masing-masing 11-12 peserta |
| 7 | Kenapa klaim di Klinik Demo Melati Jakarta Timur mencurigakan? | Agen: rekening bersama, malam dan akhir pekan, satu dokter, tagihan 5,9x |
| 8 | Apa yang harus dilakukan menurut SOP bila ada rekening dipakai banyak peserta? | Dari dokumen SOP, dengan halaman |
| 9 | Berapa kerugian dari fraud yang sudah terbukti? | Uang yang hilang |
| 10 | Lonjakan klaim DBD di awal 2026 itu wabah atau fraud? | Agen: wabah, tersebar di banyak penyedia |

Tanyakan rekening yang dipakai bersama (5, 6) **sebelum** daftar nomor rekening (6b), dan sebut "reimbursement" di 6b: hanya klaim
reimbursement yang punya rekening, dan tanpa itu klaim cashless (tanpa rekening) berada di urutan teratas. Bila ditanyakan sesudahnya, "rekening yang dipakai
bersama" dibaca sebagai nomor-nomor yang baru disebut, dan filternya tidak bisa diterapkan pada pertanyaan lanjutan.

## Opsional: data bergerak

- `scoring/service.py`: API skoring (Python standar, tanpa paket tambahan). Sebagai Application CAI: script
  `samples/health_insurance/scoring/service.py`, runtime standar, 1 vCPU / 2 GiB (membaca seluruh riwayat saat mulai, sekitar 1,1 GB,
  beberapa detik). Isi `SCORING_API_KEY` di environment Application agar setiap panggilan wajib membawa
  `Authorization: Bearer <kunci>`. Uji: `GET /health`, lalu `POST /score` dengan satu baris klaim (kolom `hi_klaim`).
- `nifi/CURSOR-BRIEF.md`: kebutuhan lingkungan NiFi di CDP. Aliran NiFi dan simulator klaim dibuat setelah lingkungannya siap.
- Untuk angka yang bergerak, matikan cache jawaban (`ANSWER_CACHE=off`) dan pakai Ask Data, bukan Home (Home disimpan per versi model).

# Brief untuk Cursor: menyiapkan NiFi untuk demo klaim kesehatan (opsional)

Dokumen ini untuk Cursor (atau siapa pun) yang menyiapkan NiFi di lingkungan CDP. Bagian ini **opsional**: tanpa NiFi, demo tetap
lengkap dengan data historis, alert dan investigasi. NiFi menambahkan "data bergerak": klaim baru masuk, diberi skor, dan terlihat
di Ask Data dalam hitungan menit.

Aliran NiFi-nya sendiri tidak dibuat di sini. Setelah lingkungan siap dan laporan di bagian 5 dikembalikan, aliran dibuat dan diuji
dari repo `cloudera-ai-studio` (folder `samples/health_insurance/nifi/`). Aliran yang sudah jadi dan diuji ada di
`flow/insurance_claims_demo.json`, dengan langkah memasangnya di `README.md` folder ini.

## 1. Prompt siap tempel

```
Siapkan NiFi di lingkungan CDP saya untuk demo streaming klaim asuransi kesehatan. Ikuti samples/health_insurance/nifi/CURSOR-BRIEF.md
di repo cloudera-ai-studio. Kerjakan bagian 2 sampai 4, jangan membuat aliran NiFi untuk demo, jangan mengubah tabel, schema atau
catalog lain selain yang disebut. Jangan menulis password atau token di chat atau di file: simpan sebagai variabel lingkungan dan
sebutkan namanya saja. Akhiri dengan laporan sesuai bagian 5.
```

## 2. Yang harus ada

| # | Kebutuhan | Kenapa |
|---|---|---|
| 1 | NiFi yang berjalan: Cloudera DataFlow (deployment) atau Flow Management Data Hub. Sebutkan mana yang dipakai dan versinya. | Prosesor yang tersedia bergantung jenis dan versi |
| 2 | **NiFi menulis ke catalog Iceberg yang sama dengan yang dibaca Trino (CDW)**: metastore yang sama dan lokasi penyimpanan yang sama. | Tanpa ini, baris yang ditulis NiFi tidak terlihat di Trino dan demo gagal |
| 3 | Akun layanan NiFi dengan hak **tambah baris** hanya ke schema demo (`<catalog>.<schema>` tempat `load_health_insurance.py` memuat data), tanpa hak hapus atau ubah skema. | Membatasi dampak bila ada salah konfigurasi |
| 4 | NiFi bisa memanggil API skoring (Application CAI `scoring/service.py`) lewat HTTPS. | Aliran memberi skor setiap klaim sebelum disimpan |
| 5 | Ada endpoint penerima (misalnya prosesor ListenHTTP) yang bisa dijangkau dari Session CAI, dengan autentikasi. | Simulator klaim dijalankan dari Session CAI |
| 6 | REST API NiFi bisa dijangkau dari Session CAI, dengan autentikasi (token atau akun). | Aliran dipasang dan diuji dari repo, bukan diklik manual |

## 3. Uji asap (wajib sebelum melapor)

1. Lewat Trino, buat tabel uji kecil di schema demo: `CREATE TABLE <catalog>.<schema>.hi_uji_nifi (id VARCHAR, waktu TIMESTAMP(3))`.
2. Lewat NiFi, tulis **satu baris** ke tabel itu.
3. Lewat Trino, `SELECT * FROM <catalog>.<schema>.hi_uji_nifi` harus menampilkan baris tersebut. Catat berapa detik sampai terlihat.
4. Hapus tabel uji lewat Trino.

Bila langkah 3 tidak menampilkan baris, kebutuhan nomor 2 belum terpenuhi. Jangan lanjut.

## 4. Batasan

- Jangan membuat, mengubah atau menghapus tabel `hi_*` lain dan view `v_hi_*`. Skema dimiliki Trino (lihat `KONTRAK-DATA.md`).
- Jangan menulis kredensial ke repo, ke chat, atau ke log.
- Jangan mengubah konfigurasi CDW atau Trino yang dipakai demo lain.

## 5. Laporan yang dikembalikan

| Isi | Contoh bentuk |
|---|---|
| Jenis dan versi NiFi | "Flow Management Data Hub, NiFi 1.x" atau "Cloudera DataFlow, NiFi 2.x" |
| Prosesor untuk menulis Iceberg yang tersedia | nama prosesor dan layanan catalog yang dipakai |
| URL REST API NiFi dan cara autentikasinya | URL; "token di variabel NIFI_TOKEN" |
| URL endpoint penerima klaim dan autentikasinya | URL; nama variabel kredensial |
| Catalog dan schema Iceberg yang dipakai | `<catalog>.<schema>` |
| Hasil uji asap | baris terlihat di Trino setelah ... detik |
| Nama variabel lingkungan yang berisi rahasia | tanpa nilainya |

## 6. Rencana aliran (untuk tahap berikutnya, bukan untuk Cursor)

```
Simulator (Session CAI) -> endpoint penerima NiFi -> validasi skema (kolom hi_klaim) -> panggil POST /score
  -> tulis klaim ke hi_klaim
  -> bila respons berisi "alert": tulis objek alert ke hi_alert
```

Kontrak event dan baris alert ada di `KONTRAK-DATA.md`. Nama prosesor pastinya dipilih setelah laporan bagian 5, sesuai versi NiFi
yang tersedia.

# Kontrak data: klaim asuransi kesehatan

Kontrak ini berlaku untuk semua yang menulis atau membaca data sample ini: generator, pemuat, model skoring, semantic model, dan
aliran NiFi nanti. Sumber kebenarannya ada di kode: kolom di `warehouse.py`, nilai di `generate_data.py`. Kalau keduanya berubah,
dokumen ini ikut diubah.

Semua data **sintetis**. Nama penyedia selalu "RS Demo ..." atau "Klinik Demo ...", dokter berupa kode, perusahaan pemegang polis
"PT Demo ...". Nomor telepon dan rekening disimpan sebagai hash (`TEL-...`, `REK-...`) dari nomor karangan.

## Aturan

1. **Hanya tambah.** Tabel tidak pernah di-update. Fakta baru adalah baris baru: hasil investigasi kedua untuk alert yang sama
   adalah baris baru di `hi_hasil_investigasi`, dan view memakai yang terakhir.
2. **Trino pemilik skema.** Tabel dibuat oleh `load_health_insurance.py` (lewat Trino). Penulis lain (NiFi) hanya menambah baris
   dan tidak mengubah kolom.
3. **Analisis membaca view**, bukan tabel. View menggabungkan tabel dan menghitung tanda keterkaitan, sehingga baris yang datang
   belakangan ikut terhitung.
4. **Satu alert per klaim.** Skor ulang untuk klaim yang sama tidak membuat alert kedua (`id_alert` = `ALR-` + nomor klaim untuk
   aliran langsung).

## Tabel

| Tabel | Satu baris adalah | Kunci | Ukuran awal |
|---|---|---|---|
| `hi_peserta` | peserta (tertanggung) | `id_peserta` | 120.000 |
| `hi_penyedia` | rumah sakit atau klinik | `kode_penyedia` | 189 |
| `hi_dokter` | dokter di satu penyedia | `kode_dokter` | 2.202 |
| `hi_diagnosis` | kode diagnosis (subset ICD-10 umum) | `kode_diagnosis` | 26 |
| `hi_klaim` | klaim (partisi per bulan `tanggal_masuk`) | `id_klaim` | ±409.000 |
| `hi_premi_bulanan` | premi diperoleh per bulan dan produk | `bulan, produk` | 115 |
| `hi_alert` | alert dari model skoring | `id_alert` | ±12.500 |
| `hi_hasil_investigasi` | hasil pemeriksaan sebuah alert, pada satu waktu | `id_alert, waktu_hasil` | ±20.000 |
| `hi_klaim_baru` | klaim yang baru masuk lewat aliran NiFi (kolom dan partisi sama dengan `hi_klaim`) | `id_klaim` | 0 |
| `hi_alert_baru` | alert untuk klaim yang baru masuk (kolom sama dengan `hi_alert`) | `id_alert` | 0 |

### `hi_klaim` (yang dikirim aliran langsung, satu event = satu baris)

| Kolom | Tipe | Isi |
|---|---|---|
| `id_klaim` | VARCHAR | `KLM-` + 7 digit |
| `id_peserta` | VARCHAR | ke `hi_peserta` |
| `kode_penyedia` | VARCHAR | ke `hi_penyedia` |
| `kode_dokter` | VARCHAR | ke `hi_dokter` |
| `tanggal_masuk`, `tanggal_keluar` | DATE | kunjungan atau rawat inap; sama untuk rawat jalan |
| `jam_kunjungan` | INTEGER | 0-23 |
| `tanggal_pengajuan` | DATE | klaim diterima asuransi (urutan kedatangan) |
| `tanggal_keputusan` | DATE | kosong selama `Diproses` |
| `jenis_layanan` | VARCHAR | `Rawat Jalan`, `Rawat Inap`, `Gawat Darurat` |
| `kode_diagnosis` | VARCHAR | ke `hi_diagnosis` |
| `tindakan_utama` | VARCHAR | misalnya `Apendektomi`, `Konsultasi dan pengobatan` |
| `lama_rawat_hari` | INTEGER | 0 untuk rawat jalan |
| `jumlah_tagihan_idr`, `jumlah_disetujui_idr`, `jumlah_dibayar_idr` | BIGINT | rupiah; disetujui dan dibayar 0 bila ditolak atau masih diproses |
| `metode_klaim` | VARCHAR | `Cashless` atau `Reimbursement` |
| `rekening_penggantian_hash` | VARCHAR | hanya untuk Reimbursement |
| `status_klaim` | VARCHAR | `Dibayar`, `Ditolak`, `Diproses` |
| `alasan_penolakan` | VARCHAR | hanya bila `Ditolak` |

### `hi_alert` (dikembalikan API skoring sebagai objek `alert`, siap ditambahkan)

`id_alert`, `id_klaim`, `waktu_alert` (TIMESTAMP, WIB), `skor_fraud` (0-1), `tingkat_risiko` (`Tinggi` >= 0,8, `Sedang` >= 0,5),
`alasan_1`-`alasan_3` (kalimat dengan angka klaim itu), `versi_model`.

### `hi_hasil_investigasi`

`id_alert`, `waktu_hasil`, `status_investigasi` (`Sedang diperiksa`, `Terbukti fraud`, `Bukan fraud`), `catatan`.

## View

| View | Isi |
|---|---|
| `v_hi_klaim_gabungan` | `hi_klaim` ditambah `hi_klaim_baru` (UNION ALL). Semua view lain membaca ini, jadi klaim yang baru masuk ikut di setiap jawaban |
| `v_hi_alert_gabungan` | `hi_alert` ditambah `hi_alert_baru` |
| `v_hi_klaim` | klaim + penyedia, dokter, diagnosis, peserta, alert terakhir, dan tanda keterkaitan: `peserta_per_rekening`, `rekening_dipakai_bersama` (`Rekening dipakai bersama` bila 3 peserta atau lebih, `Rekening sendiri`, `Tanpa rekening (Cashless)`), `telepon_dipakai_bersama`, `klaim_dokter_hari_itu`, `klaim_ganda` (kunjungan sama di dua penyedia), `rawat_ulang_7_hari`, `hari_kunjungan`, `jenis_hari`, `waktu_kunjungan`, `hari_sampai_pengajuan`, `hari_sampai_keputusan` |
| `v_hi_alert` | alert + status investigasi terakhir (`Belum diperiksa` bila belum ada hasil) |
| `v_hi_rasio_klaim` | premi dan klaim dibayar per bulan dan produk, untuk rasio klaim |

## Pola yang ditanam

| Pola | Di mana | Yang terlihat di warehouse |
|---|---|---|
| Upcoding | RS Demo Cendana Bekasi | tagihan rawat inap +33% dari RS kelas B lain, +41% untuk DBD dan pneumonia |
| Jaringan | Klinik Demo Melati Jakarta Timur, Juni 2026 | 70 peserta, 6 rekening, 10 nomor telepon, satu dokter, malam dan akhir pekan, tagihan rawat jalan 5,9x |
| Volume dokter | RS Demo Kenanga Surabaya, Mei 2026 | satu dokter penyakit dalam ±21 klaim per hari praktik; dokter lain paling banyak 2,5 |
| Lama rawat | RS Demo Flamboyan Medan | apendisitis 6,9 hari; rata-rata semua 3,1 |
| Klaim ganda | tersebar | 350 kunjungan diklaim lagi di penyedia lain |
| Rawat ulang | RS Demo Tanjung Makassar | 17% rawat inap kembali dalam 7 hari; penyedia lain paling tinggi 1% |
| Wabah DBD (bukan fraud) | DKI, Jawa Barat, Banten, Jawa Tengah, Jan-Mar 2026 | klaim DBD 4x tahun lalu, tersebar di 189 penyedia |

`expected_answers.py` memeriksa semua pola ini di warehouse dan gagal bila ada yang tidak muncul.

## Yang perlu dikoreksi oleh pemilik demo

Istilah industri, nama produk, alasan penolakan, dan kode diagnosis di sini dibuat agar masuk akal, bukan disalin dari perusahaan
mana pun. Koreksi di `generate_data.py` (daftar `DIAGNOSES`, `PRODUCTS`, `REJECTIONS`), lalu jalankan ulang seluruh urutan di README.

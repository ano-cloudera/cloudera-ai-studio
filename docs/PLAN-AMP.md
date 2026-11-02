# Rencana: Anywhere AI Studio menjadi AMP Cloudera AI

Dokumen kerja. Centang item saat selesai. Semua pekerjaan dilakukan di repo `cloudera-ai-studio`.

Status terakhir diperbarui: 2026-10-30. Pembersihan repo (2.5, 2.6) selesai.

## Ringkasan

- **Tujuan:** aplikasi bisa di-deploy sekali klik sebagai AMP di Cloudera AI, lengkap dengan data, semantic layer, library Knowledge, dan server MCP.
- **Sumber repo:** `github.com/ano-cloudera/cloudera-ai-studio` (sudah terjangkau dari CAI). Repo `anywhere-ai-studio` (yang sudah disubmit) tidak disentuh sampai ada instruksi.
- **Keputusan yang belum diambil:** lihat bagian "Keputusan terbuka".

## Fase 1: Celah demo

- [x] Teks Indonesia yang tersisa di backend menjadi English by default, mengikuti bahasa pertanyaan
- [x] Tip chip saat pertanyaan jelas milik model MCP atau dokumen
- [x] Nama tabel di "Data source", "1 row", pembuka jawaban RAG lebih bervariasi
- [x] Tes lama yang gagal dibenahi
- [x] Dokumen contoh Knowledge tidak ikut git (disimpan lokal, di-ignore); library diisi per PoC
- [ ] Deploy hasil fase 1 ke CAI dan uji tiga jalur (Ask Data, Knowledge, MCP)

## Fase 2: Kerangka AMP

- [x] 2.1 `.project-metadata.yaml` di root: variabel env (`TRINO_*`, kunci LLM; pakai `required` dan `default`), runtime Python 3.10 JupyterLab
- [x] 2.2 `scripts/amp/` untuk task `run_session`: Node, venv backend, Qdrant dan UI, model embedding, folder data, build Frontend
- [x] 2.3 Job `deploy-applications` (CAI API v2) menggantikan tiga task `start_application` (Qdrant, Backend, Frontend) dengan `static_subdomain`
- [x] 2.4 Launcher menurunkan URL antar-aplikasi dari `CDSW_DOMAIN` dan subdomain; `STUDIO_REPO_ROOT=/home/cdsw`
- [x] 2.5 Bersihkan repo: `testing/evidence`, sisa banking, `PROJECT_STATE.md`, `frontend/.next-dev.pid`, file `.zip` *(perlu persetujuan; satu commit yang bisa dibatalkan)*
- [x] 2.6 Perbarui `.gitignore` agar state lokal tidak ikut

## Fase 3: AMP sebagai akselerator umum (untuk setiap PoC)

Arah baru: AMP membawa **platform**, bukan satu use case. Data, semantic model, dokumen, dan server MCP dikonfigurasi per PoC lewat UI.
Bootstrap otomatis credit-risk **tidak lagi wajib**; jadi paket contoh opsional.

- [x] 3.1 (dihentikan) Penghapusan logika domain lama: sisanya dibiarkan karena masih dipakai tes dan tidak aktif untuk credit risk. Sudah dihapus: narasi durasi operasional dan service level, penjelasan konsep sell-in/sell-out dan proxy promo, perbandingan lintas domain, bank pertanyaan lama, graf domain lama dan stub PuppyGraph, katalog kemampuan domain lama. Masih ada (tidak aktif untuk credit risk):
  - [ ] perencana follow-up drill-down domain lama di `services/follow_up.py` (sekitar 1800 baris, bercampur dengan logika follow-up umum)
  - [ ] aturan perutean dan kata kunci domain lama di `semantic/context.py` dan `semantic/registry.py`
  - [ ] integrasi agen lokal opsional (`services/local_agent_client.py`, `ask_data_routing.py`, jalur `_run_via_local_agent_v3` di `chat.py`); tidak aktif tanpa `LOCAL_AGENT_BASE_URL`
  - [x] tes karakterisasi jalur credit risk (`test_credit_risk_characterization.py`) dibuat lebih dulu sebagai pengaman
- [x] 3.2a vLLM opsional (`ENABLE_VLLM`, runtime GPU `AMP_VLLM_RUNTIME_ID`, unduh model); perlu diuji di CAI dengan GPU
- [x] 3.2 Variabel env AMP tidak terikat Trino saja: Trino, Impala, PostgreSQL, dan kunci LLM; cara menambah variabel baru per PoC didokumentasikan
- [x] 3.3 Panduan "membawa AMP ke PoC baru": daftar yang diganti per PoC (sumber data, semantic model, dokumen, MCP, branding, pertanyaan awal)
- [ ] 3.4 Paket contoh opsional (credit-risk): data dan server MCP saja; PDF contoh tidak dikirim. Putuskan apakah data dan server MCP ikut di repo akselerator
- [ ] 3.5 Pertanyaan awal dan teks contoh di UI dapat diatur lewat Settings, bukan terikat ke satu domain

## Fase 6: Rilis sebagai akselerator untuk Cloudera Sales Engineer

Dikerjakan **terakhir**, setelah semua fase di atas settle di folder ini (`cloudera-ai-studio`). Lalu dipindahkan ke folder baru
`amp-anywhere-ai-studio` dengan riwayat git baru (satu commit awal), sehingga tidak ada jejak istilah lama di riwayat.

- [ ] 6.1 Semua fase 1 sampai 5 selesai dan diuji di CAI (import AMP di workspace bersih)
- [ ] 6.2 README dan panduan PoC dibaca ulang dari sudut pandang Sales Engineer (bukan pengembang)
- [ ] 6.3 Pindahkan hanya file yang dilacak ke `amp-anywhere-ai-studio` (`git archive`), `git init`, satu commit awal
- [ ] 6.4 Jalankan ulang tes backend dan frontend, build, dan pemindaian istilah lama di folder baru
- [ ] 6.5 Buat repo GitHub yang bisa dijangkau CAI, atur remote, push (dilakukan pemilik repo)
- [ ] 6.6 Uji import AMP dari repo baru di workspace CAI yang bersih
- [ ] 6.7 Aturan memori diperbarui: kerja pindah ke `amp-anywhere-ai-studio`

## Fase 4: Pertanyaan kompleks

- [x] 4.1 Patokan dijalankan (10 pertanyaan): 1 lulus, 2 setengah benar, 7 salah. Penyebab: filter nilai dimensi diabaikan, hanya satu model terpasang, perbandingan dua periode dan ambang hitungan tidak didukung, langkah bertingkat, pertanyaan multi-sumber dijawab separuh, pesan cadangan buruk
- [x] 4.2 Langkah 0: ringkasan cadangan deterministik (angka, kelompok tertinggi dan terendah, singular) dan log penyebab kegagalan model analisis (`analyze_result_failed`)
- [x] 4.3 Langkah 1: filter nilai dimensi dari data (`ask_data/value_filters.py`): nilai diambil lewat `SELECT DISTINCT` yang di-cache, kolom id, kolom rumus metrik, dan kolom kardinalitas tinggi tidak pernah difilter; filter dicantumkan di jawaban
- [x] 4.4a Langkah 2a: drill-across multi-metrik (`ask_data/drill_across.py`): metrik dikenali dari nama dan sinonim, satu query governed per metrik pada pengelompokan yang sama, digabung di Python; filter nilai ikut ke semua dataset
- [ ] 4.4b Langkah 2b: perbandingan dua periode (dua query, selisih) dan rata-rata keseluruhan sebagai pembanding (ambang "lebih dari 15 poin di bawah")
- [ ] 4.5 Langkah 3: rencana bertingkat dan penanda "bagian ini butuh chip dokumen atau model" untuk pertanyaan multi-sumber
- [ ] 4.6 Delinquency (loan_quality) harus berada di model yang sama dengan credit_applications supaya drill-across bisa menggabungkannya (saran: satu model, dua entitas). Dibuat di UI Semantic Layer oleh pemilik PoC
- [x] 4.8 Resolver umum: aturan katalog lama dan boost kata kunci demo tidak lagi memengaruhi model lain (`tests/test_generic_models.py`)
- [x] 4.9 Prompts hanya global (pilihan scope dihapus dari UI, butuh Postgres metadata); Skills disembunyikan secara default (`NEXT_PUBLIC_FEATURE_SKILLS=false`), kode tetap ada karena tidak ada jalur dari chat ke skill
- [ ] 4.7 Jalankan ulang 10 pertanyaan uji di CAI setelah tiap langkah dan catat skornya

PuppyGraph asli ditunda: hanya tersedia sebagai Docker, dan image 3 GB tidak praktis dipindah ke CAI. Infisical self-host dibatalkan (tidak praktis di CAI), kodenya sudah dihapus.

## Fase 5: Uji end-to-end *(kamu menjalankan di CAI)*

- [ ] 5.1 Import AMP di workspace CAI yang bersih
- [ ] 5.2 Kirim log tiap task yang gagal, perbaiki, ulangi
- [ ] 5.3 Jalankan skrip demo (3 pertanyaan Ask Data, 3 Knowledge, 1 MCP)
- [x] 5.4 Job `deploy-applications` (CAI API v2) sekaligus berfungsi sebagai redeploy; perlu diuji di CAI

## Kerapian (paralel)

- [ ] Tes banking lama di repo lama yang bergantung pada kunci LLM (`SECRET_NOT_FOUND`)
- [ ] Sekitar 46 error tipe TypeScript di file tes (build tidak terpengaruh)
- [x] Istilah domain lama (nama perusahaan dan jaringan ritel) dihapus dari kode, tes, prompt, dan dokumen
- [ ] Logika perutean khusus domain lama (sell-in/sell-out, DC, picking) masih ada di kode; hapus bertahap bila tidak dipakai
- [ ] Riwayat chat hanya di browser (localStorage); pertimbangkan simpan di server
- [ ] Ekspor jawaban yang rapi untuk dibagikan

## Keputusan terbuka

1. **Boleh membersihkan repo** untuk item 2.5?
2. **Siapa yang meng-import AMP?** Katalog AMP biasanya butuh akun admin.
3. **Cara mengambil ekspor semantic model** untuk item 3.2: file ekspor dari UI, atau akses ke isinya.
4. Empat commit lokal di `anywhere-ai-studio` yang belum dipush: dibiarkan, atau `git reset --hard origin/main`?

## Risiko

- Task AMP baru bisa diuji di CAI, jadi fase 2 sampai 3 akan ada beberapa putaran perbaikan.
- Belum pasti apakah import project biasa dari Git menjalankan task `.project-metadata.yaml`, atau hanya katalog AMP. Perlu dicek di workspace.
- CAI API v2 belum pernah dicoba dari sini; nama variabel kunci internal di sesi CAI perlu dipastikan.

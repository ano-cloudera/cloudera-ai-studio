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
- [ ] Pastikan library Credit Knowledge berisi dua PDF (Credit approval policy dan Credit Channel Performance), lalu uji ulang "Can we say Branch is slower because of manual review?" *(dikerjakan di UI CAI)*
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

- [ ] 3.1 Hapus sisa logika khusus domain lama di kode supaya platform netral. Sudah dihapus: narasi durasi operasional dan service level, penjelasan konsep sell-in/sell-out dan proxy promo, perbandingan lintas domain. Masih ada (tidak aktif untuk credit risk):
  - [ ] perencana follow-up drill-down domain lama di `services/follow_up.py` (sekitar 1800 baris, bercampur dengan logika follow-up umum)
  - [ ] aturan perutean dan kata kunci domain lama di `semantic/context.py` dan `semantic/registry.py`
  - [ ] bank pertanyaan lama (`data/random_queries.yaml`, `semantic/questions.py`, endpoint `/random-queries`, opsi starter `question_bank`)
  - [ ] graf domain lama (`knowledge/business_graph.yaml`, `semantic/domain_graph.py`) dan stub PuppyGraph
  - [ ] katalog kemampuan domain lama (`ask_data/capability_catalog.py`) dan integrasi agen lokal (`services/local_agent_client.py`, `ask_data_routing.py`)
  - [ ] tes karakterisasi untuk jalur credit risk dibuat lebih dulu sebelum langkah di atas, supaya penghapusan tidak merusak jawaban yang sudah benar
- [x] 3.2a vLLM opsional (`ENABLE_VLLM`, runtime GPU `AMP_VLLM_RUNTIME_ID`, unduh model); perlu diuji di CAI dengan GPU
- [ ] 3.2 Variabel env AMP tidak terikat Trino saja: Trino, Impala, PostgreSQL, dan kunci LLM; cara menambah variabel baru per PoC didokumentasikan
- [ ] 3.3 Panduan "membawa AMP ke PoC baru": daftar yang diganti per PoC (sumber data, semantic model, dokumen, MCP, branding, pertanyaan awal)
- [ ] 3.4 Paket contoh opsional (credit-risk): data, PDF, server MCP; task opsional yang berhenti sendiri kalau tidak dipakai
- [ ] 3.5 Pertanyaan awal dan teks contoh di UI dapat diatur lewat Settings, bukan terikat ke satu domain

## Fase 4: Pertanyaan kompleks

- [ ] 4.1 Jalankan lima pertanyaan uji sebagai patokan *(kamu menjalankan, saya baca hasilnya)*
  1. Which region has a below-average approval rate and an above-average delinquency rate?
  2. For the region with the lowest approval rate, show its delinquency rate and average decision time by channel.
  3. How did the approval rate by region change between March to May and June to August 2026, and which region moved the most?
  4. Which region and channel combinations are more than 15 percentage points below the overall approval rate, and does the policy say that triggers an investigation?
  5. What share of approvals in Jawa Barat Digital were policy exceptions, and what does the approval policy say about them?
- [ ] 4.2 Graph konteks bisnis di backend (YAML): entitas, kunci join, konsep yang terhubung ke dokumen dan model MCP
- [ ] 4.3 Pemecahan pertanyaan lintas tabel dan lintas sumber memakai graph itu
- [ ] 4.4 Tes untuk lima pertanyaan di atas

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

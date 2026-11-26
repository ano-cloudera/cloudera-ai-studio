#!/usr/bin/env python3
"""Write the documents of the health insurance sample as PDF (synthetic, for a Knowledge library).

    python3 samples/health_insurance/docs/build_docs.py      # writes the three PDFs next to this script

Upload them to a Knowledge library (Knowledge -> New library -> Upload). The agent then cites them, with the page, when it says what
to do about a suspicious provider or how a claim should have been handled. Their rules and thresholds match the data and the example
scoring model: the alert levels (0.5 and 0.8), a bank account shared by 3 members or more, a readmission within 7 days, the decision
times of the claims, the exclusion of general check-ups. Needs fpdf2 (in the Backend's requirements).
"""
from __future__ import annotations

from pathlib import Path

from fpdf import FPDF

HERE = Path(__file__).resolve().parent
NOTE = "Dokumen contoh (sintetis) untuk demo Anywhere AI Studio. Bukan dokumen resmi perusahaan mana pun."
COMPANY = "PT Asuransi Kesehatan Demo"

POLICY = {
    "file": "Ketentuan_Polis_Asuransi_Kesehatan.pdf",
    "title": "Ketentuan Umum Polis Asuransi Kesehatan",
    "code": "POL-KES-001 Rev. 4",
    "sections": [
        ("1. Pihak dan Produk", [
            f"Polis ini diterbitkan oleh {COMPANY} (Penanggung) untuk Pemegang Polis dan Peserta yang tercantum dalam daftar peserta.",
            "Produk individu: Sehat Silver (limit tahunan Rp 150 juta), Sehat Gold (Rp 300 juta), Sehat Platinum (Rp 1 miliar). Produk "
            "korporat (kumpulan): Kumpulan Standar (Rp 100 juta per peserta) dan Kumpulan Eksekutif (Rp 400 juta per peserta).",
        ]),
        ("2. Manfaat yang Ditanggung", [
            "Rawat inap: biaya kamar, dokter, tindakan, obat dan pemeriksaan penunjang selama perawatan yang diperlukan secara medis.",
            "Rawat jalan: konsultasi dokter umum dan spesialis, obat, serta tindakan rawat jalan seperti hemodialisis dan kemoterapi.",
            "Gawat darurat: penanganan di instalasi gawat darurat, termasuk di penyedia di luar jaringan rekanan.",
            "Lama perawatan yang ditanggung adalah lama yang diperlukan secara medis untuk diagnosis tersebut. Hari perawatan yang tidak "
            "didukung kebutuhan medis tidak ditanggung.",
        ]),
        ("3. Cara Klaim", [
            "Cashless: Peserta menunjukkan kartu peserta di penyedia rekanan; penyedia menagih langsung kepada Penanggung.",
            "Reimbursement (penggantian biaya): Peserta membayar lebih dahulu, lalu mengajukan klaim paling lambat 30 hari setelah pulang "
            "atau setelah kunjungan, dengan kuitansi asli, rincian biaya, resume medis dan hasil pemeriksaan. Penggantian dibayarkan ke "
            "rekening atas nama Peserta atau Pemegang Polis.",
            "Satu kunjungan atau satu perawatan hanya dapat diklaim satu kali. Klaim kedua atas kunjungan yang sama, di penyedia yang sama "
            "atau berbeda, ditolak.",
        ]),
        ("4. Pengecualian", [
            "4.1 Pemeriksaan kesehatan umum (medical check-up) tanpa keluhan, kecuali dinyatakan lain pada produk.",
            "4.2 Penyakit yang timbul dalam masa tunggu: 30 hari sejak polis berlaku untuk penyakit umum, dan 12 bulan untuk batu empedu, "
            "penyakit ginjal kronis, kanker dan persalinan.",
            "4.3 Perawatan atau tindakan yang tidak diperlukan secara medis, termasuk rawat inap untuk keadaan yang lazim ditangani rawat jalan.",
            "4.4 Biaya yang timbul dari keterangan yang tidak benar, dokumen yang dipalsukan, atau kerja sama yang tidak wajar antara Peserta "
            "dan penyedia.",
        ]),
        ("5. Hak Penanggung atas Klaim yang Tidak Wajar", [
            "Penanggung berhak menunda pembayaran klaim untuk pemeriksaan, meminta rekam medis kepada penyedia, dan menolak klaim yang tidak "
            "sesuai ketentuan. Klaim yang telah dibayar lalu terbukti tidak sah wajib dikembalikan kepada Penanggung.",
        ]),
    ],
}

SOP_CLAIMS = {
    "file": "SOP_Penanganan_Klaim_Kesehatan.pdf",
    "title": "SOP Penanganan Klaim Asuransi Kesehatan",
    "code": "SOP-KLM-010 Rev. 2",
    "sections": [
        ("1. Tujuan", [
            "Mengatur penerimaan, pemeriksaan dan keputusan klaim cashless dan reimbursement agar tepat waktu, sesuai polis dan terkendali "
            "dari risiko fraud.",
        ]),
        ("2. Target Waktu Keputusan", [
            "Cashless: keputusan paling lambat 5 hari kerja sejak tagihan penyedia diterima.",
            "Reimbursement: keputusan paling lambat 14 hari kerja sejak berkas lengkap. Klaim di atas Rp 30 juta boleh ditambah 3 hari kerja "
            "untuk telaah medis.",
            "Klaim dengan alert fraud tingkat Tinggi ditunda pembayarannya sampai pemeriksaan sesuai SOP Investigasi Fraud Klaim selesai.",
        ]),
        ("3. Pemeriksaan Klaim", [
            "3.1 Kelengkapan dokumen dan kesesuaian dengan masa tunggu dan limit tahunan.",
            "3.2 Kesesuaian diagnosis, tindakan dan lama rawat. Tagihan dibandingkan dengan rata-rata penyedia sekelas untuk diagnosis dan "
            "layanan yang sama; lama rawat dibandingkan dengan lama rawat yang lazim untuk diagnosis tersebut.",
            "3.3 Alert dari model skoring fraud dibaca beserta alasannya sebelum keputusan diambil.",
        ]),
        ("4. Alasan Penolakan", [
            "Dokumen tidak lengkap; masa tunggu belum terpenuhi; melebihi limit tahunan; di luar pertanggungan (misalnya pemeriksaan "
            "kesehatan umum); klaim ganda atas kunjungan yang sama; terbukti fraud.",
        ]),
        ("5. Pemantauan", [
            "Setiap bulan Kepala Divisi Klaim meninjau rasio klaim per produk (target di bawah 75 persen), tingkat penolakan, waktu keputusan "
            "rata-rata, dan tingkat alert per penyedia.",
        ]),
    ],
}

SOP_FRAUD = {
    "file": "SOP_Investigasi_Fraud_Klaim.pdf",
    "title": "SOP Investigasi Fraud Klaim Kesehatan",
    "code": "SOP-SIU-003 Rev. 3",
    "sections": [
        ("1. Tujuan dan Ruang Lingkup", [
            "Prosedur ini mengatur cara Unit Investigasi Khusus (SIU) memeriksa klaim yang ditandai alert fraud, menyimpulkan hasilnya, dan "
            "menindaklanjuti peserta, dokter atau penyedia yang terlibat. Berlaku untuk semua produk individu dan korporat.",
        ]),
        ("2. Alert dan Prioritas", [
            "Model skoring fraud memberi setiap klaim skor 0 sampai 1 dan tiga alasan utama. Skor 0,8 atau lebih adalah risiko Tinggi; skor "
            "0,5 sampai di bawah 0,8 adalah risiko Sedang; di bawah 0,5 tidak menaikkan alert.",
            "Risiko Tinggi: pembayaran ditunda dan pemeriksaan dimulai paling lambat 2 hari kerja. Risiko Sedang: pemeriksaan dimulai paling "
            "lambat 5 hari kerja. Prioritas pertama adalah klaim berisiko Tinggi dengan nilai tagihan terbesar.",
            "Model saat ini adalah model contoh. Keputusan akhir selalu diambil investigator berdasarkan bukti, bukan skor.",
        ]),
        ("3. Tanda Bahaya", [
            "3.1 Rekening penggantian yang menerima penggantian untuk 3 peserta atau lebih (rekening dipakai bersama).",
            "3.2 Nomor telepon yang dipakai 3 peserta atau lebih.",
            "3.3 Dokter dengan lebih dari 30 klaim per hari praktik dari peserta kita.",
            "3.4 Tagihan lebih dari 1,3 kali rata-rata penyedia sekelas untuk diagnosis dan layanan yang sama (indikasi upcoding).",
            "3.5 Lama rawat lebih dari 1,5 kali lama rawat yang lazim untuk diagnosis tersebut.",
            "3.6 Rawat inap ulang untuk diagnosis yang sama dalam 7 hari setelah pulang.",
            "3.7 Kunjungan yang sama diklaim di dua penyedia (klaim ganda).",
            "3.8 Kunjungan rawat jalan yang terkumpul di akhir pekan dan malam hari di satu klinik.",
        ]),
        ("4. Langkah Investigasi", [
            "4.1 Verifikasi dokumen: keaslian kuitansi, kesesuaian tanggal, diagnosis dan tindakan.",
            "4.2 Konfirmasi ke penyedia: minta rekam medis dan daftar kunjungan dokter pada tanggal tersebut.",
            "4.3 Analisis keterkaitan: kelompokkan klaim menurut rekening penggantian, nomor telepon, dokter dan penyedia untuk melihat "
            "apakah ada jaringan. Bila satu rekening atau satu dokter terkait banyak klaim, periksa seluruh klaim yang terkait, bukan hanya "
            "klaim yang menaikkan alert.",
            "4.4 Kunjungan lapangan dan wawancara peserta bila bukti dokumen belum cukup.",
            "4.5 Kesimpulan paling lambat 30 hari sejak alert: Terbukti fraud atau Bukan fraud, dengan catatan bukti.",
        ]),
        ("5. Tindak Lanjut", [
            "Terbukti fraud: klaim ditolak atau, bila sudah dibayar, ditagih kembali (recovery); peserta dapat diakhiri kepesertaannya; "
            "temuan dilaporkan sesuai ketentuan yang berlaku.",
            "Penyedia: bila tingkat alert penyedia lebih dari 10 persen dalam satu bulan, atau ada fraud terbukti yang melibatkan dokter atau "
            "manajemennya, lakukan audit klaim penyedia, hentikan sementara layanan cashless, dan pertimbangkan pemutusan kerja sama.",
            "Bukan fraud: pembayaran dilanjutkan tanpa menunggu siklus berikutnya, dan alasan alert dicatat untuk perbaikan model.",
        ]),
        ("6. Lonjakan Klaim karena Wabah", [
            "Lonjakan klaim karena wabah, misalnya demam berdarah dengue (DBD) di musim hujan, biasanya tersebar di banyak penyedia dan dokter "
            "sesuai jumlah peserta di wilayah itu. Lonjakan seperti ini tidak otomatis dianggap fraud: percepat keputusan klaim cashless, dan "
            "periksa hanya penyedia yang tagihannya atau porsinya menyimpang dari penyedia lain di wilayah yang sama.",
            "Lonjakan yang terkumpul di satu atau dua penyedia, satu dokter, atau satu rekening diperlakukan sebagai tanda bahaya.",
        ]),
        ("7. Pelaporan", [
            "SIU melaporkan setiap bulan: jumlah alert, tingkat alert terbukti, kerugian fraud terbukti, nilai recovery, dan potensi kerugian "
            "dari alert berisiko Tinggi yang belum selesai diperiksa.",
        ]),
    ],
}


class Document(FPDF):
    def __init__(self, title: str, code: str) -> None:
        super().__init__(format="A4")
        self.doc_title, self.code = title, code
        self.set_auto_page_break(auto=True, margin=22)
        self.set_margins(22, 20, 22)

    def header(self) -> None:
        self.set_font("Helvetica", "B", 9)
        self.set_text_color(90, 90, 110)
        self.cell(0, 6, f"{COMPANY}  |  {self.doc_title}  |  {self.code}", new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(220, 220, 230)
        self.line(22, self.get_y(), 188, self.get_y())
        self.ln(4)

    def footer(self) -> None:
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(130, 130, 140)
        self.cell(0, 6, f"{NOTE}   Halaman {self.page_no()}", align="C")


def build(spec: dict) -> Path:
    pdf = Document(spec["title"], spec["code"])
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 17)
    pdf.set_text_color(21, 8, 74)
    pdf.multi_cell(0, 9, spec["title"], new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(90, 90, 110)
    pdf.multi_cell(0, 6, f"Nomor dokumen: {spec['code']}   Berlaku sejak: 1 Januari 2025", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    for heading, paragraphs in spec["sections"]:
        if pdf.get_y() > 245:
            pdf.add_page()
        pdf.set_font("Helvetica", "B", 12)
        pdf.set_text_color(21, 8, 74)
        pdf.multi_cell(0, 7, heading, new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 10.5)
        pdf.set_text_color(40, 40, 50)
        for paragraph in paragraphs:
            pdf.multi_cell(0, 5.6, paragraph, new_x="LMARGIN", new_y="NEXT")
            pdf.ln(1.5)
        pdf.ln(2)
    out = HERE / spec["file"]
    pdf.output(str(out))
    return out


def main() -> int:
    for spec in (POLICY, SOP_CLAIMS, SOP_FRAUD):
        path = build(spec)
        print(f"{path.name}: {path.stat().st_size // 1024} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

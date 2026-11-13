#!/usr/bin/env python3
"""Write the two sample SOP documents of the fuel distribution demo as PDF (synthetic, for the Knowledge library).

    python3 samples/fuel_distribution/docs/build_sop_pdfs.py      # writes the two PDFs next to this script

Upload both to a Knowledge library (Knowledge -> New library -> Upload). The agent then cites them, with the page, when it
recommends what to do; their thresholds match the planted patterns of generate_data.py. Needs fpdf2 (pip install fpdf2).
"""
from __future__ import annotations

from pathlib import Path

from fpdf import FPDF

HERE = Path(__file__).resolve().parent
NOTE = "Dokumen contoh (sintetis) untuk demo Anywhere AI Studio. Bukan dokumen resmi."

SOP_DELIVERY = {
    "file": "SOP_Penanganan_Keterlambatan_Penyaluran_BBM.pdf",
    "title": "SOP Penanganan Keterlambatan Penyaluran BBM",
    "code": "SOP-DIST-014 Rev. 3",
    "sections": [
        ("1. Tujuan", [
            "Prosedur ini mengatur cara memantau, mengeskalasi dan menindaklanjuti keterlambatan penyaluran BBM dari Terminal BBM (TBBM) ke SPBU dan pelanggan industri, agar pasokan ke konsumen tidak terganggu.",
        ]),
        ("2. Ruang Lingkup", [
            "Berlaku untuk seluruh Loading Order (LO) yang dikirim dengan mobil tangki dari TBBM di semua regional, untuk SPBU tipe COCO, CODO dan DODO serta pelanggan industri.",
        ]),
        ("3. Definisi", [
            "Loading Order (LO): perintah muat satu pengiriman dari TBBM ke satu SPBU atau pelanggan.",
            "SLA pengiriman: batas waktu tempuh dalam menit sejak mobil tangki keluar TBBM, ditetapkan per rute berdasarkan jarak standar.",
            "Terlambat: LO yang tiba melebihi SLA pengiriman. Tingkat keterlambatan adalah jumlah LO terlambat dibagi jumlah LO yang selesai, dalam persen.",
        ]),
        ("4. Ambang Batas dan Eskalasi", [
            "Tingkat keterlambatan dipantau per TBBM dan per regional setiap bulan, terhadap target nasional 15%.",
            "Level 1 - Waspada: tingkat keterlambatan TBBM di atas 20% dalam satu bulan. Penanggung jawab: Terminal Manager. Tindak lanjut dalam 3 hari kerja dengan rencana perbaikan tertulis.",
            "Level 2 - Kritis: tingkat keterlambatan TBBM di atas 30% dalam satu bulan, atau regional di atas 25%. Penanggung jawab: Regional Distribution Manager. Tiket tindak lanjut prioritas tinggi dibuat dalam 24 jam dan ditinjau mingguan.",
            "Level 3 - Darurat: tingkat keterlambatan di atas 25% selama dua bulan berturut-turut, atau terjadi kekosongan stok di SPBU akibat keterlambatan. Penanggung jawab: VP Distribution. Rapat penanganan dalam 48 jam.",
        ]),
        ("5. Langkah Penanganan", [
            "5.1 Identifikasi sumber: pecah keterlambatan per rute, per tipe SPBU, per mobil tangki dan per jam muat untuk menemukan titik konsentrasi.",
            "5.2 Armada: audit kesiapan mobil tangki (utilisasi di atas 85% atau umur kendaraan di atas 10 tahun), tambah unit sewa bila perlu.",
            "5.3 Penjadwalan: geser slot muat ke luar jam padat; untuk rute dengan jarak di atas 300 km jadwalkan pemberangkatan malam.",
            "5.4 Rute: untuk wilayah kepulauan dan pedalaman (misalnya Papua Maluku dan Kalimantan) evaluasi rute alternatif atau titik serah antara.",
            "5.5 SPBU DODO: karena dikelola mitra, tetapkan jadwal kirim tetap dan buffer stok minimal 2 hari; koordinasikan melalui Sales Area Manager.",
            "5.6 Komunikasi: informasikan SPBU terdampak dan pelanggan industri bila keterlambatan diperkirakan lebih dari 2 jam.",
        ]),
        ("6. Pelaporan", [
            "Terminal Manager melaporkan status tindak lanjut setiap minggu. Regional Distribution Manager menyampaikan ringkasan bulanan tingkat keterlambatan per TBBM, penyebab utama dan status tiket ke VP Distribution.",
            "Setiap tindak lanjut dicatat sebagai tiket di Operations Desk dengan lokasi, prioritas, penanggung jawab, tenggat dan bukti angka.",
        ]),
        ("7. Tanggung Jawab", [
            "Terminal Manager: pemantauan harian TBBM, tindak lanjut Level 1.",
            "Regional Distribution Manager: eskalasi Level 2, alokasi armada antar TBBM dalam regional.",
            "VP Distribution: keputusan Level 3, penambahan armada dan perubahan rute lintas regional.",
        ]),
    ],
}

SOP_QUOTA = {
    "file": "Pedoman_Pengendalian_Kuota_BBM_Subsidi.pdf",
    "title": "Pedoman Pengendalian Kuota BBM Subsidi",
    "code": "PDM-KUOTA-007 Rev. 2",
    "sections": [
        ("1. Tujuan", [
            "Pedoman ini mengatur pemantauan realisasi penyaluran BBM bersubsidi terhadap kuota, agar penyaluran tepat sasaran dan tidak melampaui kuota yang ditetapkan.",
        ]),
        ("2. Produk dan Istilah", [
            "BBM subsidi dalam pedoman ini: Pertalite (Jenis BBM Khusus Penugasan) dan Biosolar (Jenis BBM Tertentu).",
            "Kuota: volume yang ditetapkan per produk, per provinsi, per bulan, dalam kiloliter (KL).",
            "Pencapaian kuota: realisasi penyaluran dibagi kuota, dalam persen.",
        ]),
        ("3. Ambang Pemantauan", [
            "Normal: pencapaian kuota 80% sampai 95% pada akhir bulan.",
            "Peringatan: pencapaian kuota di atas 95% sebelum akhir bulan. Region Manager memperketat verifikasi pembelian di SPBU dan memantau SPBU dengan penjualan subsidi tidak wajar.",
            "Melampaui kuota: pencapaian kuota di atas 100%. Wajib dibuat tiket prioritas tinggi; Region Manager mengajukan penyesuaian alokasi ke kantor pusat dan menindak SPBU dengan anomali transaksi.",
            "Serapan rendah: pencapaian kuota di bawah 80%. Evaluasi ketersediaan stok dan keterlambatan pasokan di wilayah tersebut, karena serapan rendah dapat berarti pasokan yang tidak sampai, bukan permintaan yang rendah.",
        ]),
        ("4. Langkah Pengendalian", [
            "4.1 Verifikasi: wajibkan verifikasi digital (kode QR kendaraan) untuk pembelian Biosolar dan Pertalite di wilayah dengan status Peringatan.",
            "4.2 Pengawasan SPBU: SPBU dengan porsi penjualan subsidi di atas 90% dari total penjualannya selama dua bulan diperiksa oleh tim pengawasan.",
            "4.3 Realokasi: pengalihan sisa kuota antar provinsi dalam satu regional dapat diajukan Region Manager, dengan persetujuan kantor pusat.",
            "4.4 Koordinasi: perubahan kuota tahunan dikoordinasikan oleh kantor pusat dengan regulator.",
        ]),
        ("5. Pelaporan", [
            "Laporan realisasi kuota per produk dan per provinsi disusun setiap minggu dan setiap bulan. Wilayah dengan status Peringatan, Melampaui kuota atau Serapan rendah dilaporkan dengan rencana tindak lanjut dan tiket di Operations Desk.",
        ]),
        ("6. Tanggung Jawab", [
            "Sales Area Manager: pemantauan SPBU dan verifikasi pembelian.",
            "Region Manager: status pencapaian kuota per provinsi, pengajuan realokasi, tindak lanjut anomali.",
            "Kantor Pusat (Fuel Retail Marketing): persetujuan realokasi dan koordinasi kuota tahunan.",
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
        self.cell(0, 6, f"{self.doc_title}  |  {self.code}", new_x="LMARGIN", new_y="NEXT")
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
    for spec in (SOP_DELIVERY, SOP_QUOTA):
        print(build(spec))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

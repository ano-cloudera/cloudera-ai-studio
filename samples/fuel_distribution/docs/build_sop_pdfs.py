#!/usr/bin/env python3
"""Write the sample documents of the fuel distribution demo as PDF (synthetic, for the Knowledge library).

    python3 samples/fuel_distribution/docs/build_sop_pdfs.py      # writes the four PDFs next to this script

Upload them to a Knowledge library (Knowledge -> New library -> Upload). The agent then cites them, with the page, when it
recommends what to do. Their thresholds and figures match generate_data.py and the semantic model (the SLA formula, the
backup terminal of Kertapati, the reasons of a late order). Needs fpdf2 (pip install fpdf2).
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


SOP_OUTAGE = {
    "file": "SOP_Pengalihan_Pasokan_Gangguan_TBBM.pdf",
    "title": "SOP Pengalihan Pasokan Saat Gangguan TBBM",
    "code": "SOP-DIST-021 Rev. 1",
    "sections": [
        ("1. Tujuan", [
            "Prosedur ini mengatur pengalihan pasokan BBM ke SPBU dan pelanggan industri ketika sebuah Terminal BBM (TBBM) tidak bisa melayani sebagian atau seluruh kapasitasnya, agar stok di SPBU tidak habis.",
        ]),
        ("2. Ruang Lingkup", [
            "Berlaku untuk gangguan TBBM karena kerusakan fasilitas, perbaikan terjadwal yang melebihi kapasitas cadangan, atau kondisi di luar kendali seperti bencana dan cuaca ekstrem di lokasi TBBM.",
        ]),
        ("3. Definisi", [
            "Gangguan parsial: kapasitas muat TBBM turun kurang dari 50 persen.",
            "Gangguan penuh: TBBM tidak dapat memuat sama sekali selama lebih dari 24 jam.",
            "TBBM cadangan: TBBM yang ditetapkan dalam peta cadangan untuk melayani pelanggan tertentu bila TBBM asalnya terganggu.",
            "Pengalihan pasokan: pengiriman LO dari TBBM cadangan ke pelanggan yang biasanya dilayani TBBM asal.",
        ]),
        ("4. Peta TBBM Cadangan", [
            "Kertapati (Palembang) dicadangkan oleh TBBM Panjang (Bandar Lampung) untuk pelanggan di Sumatera Selatan, Bengkulu dan Bangka Belitung. Jarak tempuh dari Panjang dapat mencapai 1,8 kali jarak standar pelanggan.",
            "Plumpang (Jakarta Utara) dicadangkan oleh Tanjung Gerem (Cilegon) untuk pelanggan di DKI Jakarta dan Jawa Barat bagian utara.",
            "Tanjung Batu (Balikpapan) dicadangkan oleh Banjarmasin untuk pelanggan di Kalimantan Timur.",
            "Peta cadangan ditinjau setiap triwulan oleh Regional Distribution Manager bersama Terminal Manager masing-masing TBBM.",
        ]),
        ("5. Langkah Penanganan", [
            "5.1 Tetapkan status gangguan dalam dua jam sejak TBBM melapor. Terminal Manager menyampaikan kapasitas yang tersisa; Regional Distribution Manager menetapkan status.",
            "5.2 Prioritaskan SPBU DODO dan pelanggan industri yang stoknya kurang dari dua hari untuk dialihkan lebih dulu.",
            "5.3 Alihkan pengiriman ke TBBM cadangan sesuai peta. Jadwalkan ulang slot muat di TBBM cadangan agar tidak menumpuk pada jam padat.",
            "5.4 Tambah mobil tangki dari TBBM lain dalam regional bila TBBM cadangan tidak mampu menanggung seluruh pengalihan.",
            "5.5 Beri tahu SPBU dan pelanggan industri terdampak bila keterlambatan diperkirakan lebih dari dua jam.",
            "5.6 Catat setiap pengiriman hasil pengalihan dengan alasan Pasokan dari terminal alternatif, agar dapat dipisahkan dari keterlambatan biasa.",
        ]),
        ("6. Ketentuan SLA Selama Pengalihan", [
            "SLA pengiriman tidak berubah secara otomatis. Batas waktu tetap dihitung dari jarak standar pelanggan dari TBBM asal, sesuai SOP keterlambatan.",
            "Pengalihan yang tempuhnya lebih dari 1,5 kali jarak standar dicatat sebagai pengecualian dan ditinjau oleh Regional Distribution Manager dalam tujuh hari kerja. Peninjauan dapat menetapkan SLA baru untuk rute tersebut selama gangguan.",
        ]),
        ("7. Pelaporan dan Penutupan", [
            "Selama gangguan, Terminal Manager TBBM cadangan melaporkan tingkat keterlambatan harian rute pengalihan kepada Regional Distribution Manager.",
            "Gangguan ditutup setelah TBBM asal kembali memuat normal. Tingkat keterlambatan rute pengalihan pada bulan tersebut dibandingkan dengan bulan sebelum gangguan dan dilaporkan ke VP Distribution.",
        ]),
        ("8. Tanggung Jawab", [
            "Terminal Manager TBBM asal: status kapasitas dan laporan harian gangguan.",
            "Terminal Manager TBBM cadangan: penjadwalan slot muat dan laporan rute pengalihan.",
            "Regional Distribution Manager: penetapan status, keputusan pengalihan dalam regional, dan peninjauan pengecualian SLA.",
            "VP Distribution: keputusan untuk gangguan penuh yang berlangsung lebih dari tujuh hari, dan pengalihan lintas regional.",
        ]),
    ],
}

SOP_SLA = {
    "file": "Standar_Layanan_Pengiriman_LO.pdf",
    "title": "Standar Layanan Pengiriman Loading Order BBM",
    "code": "PDM-LAYANAN-003 Rev. 1",
    "sections": [
        ("1. Tujuan", [
            "Standar ini menetapkan cara batas waktu pengiriman (SLA) dihitung untuk setiap Loading Order (LO), sehingga setiap pihak menilai ketepatan pengiriman dengan cara yang sama.",
        ]),
        ("2. Ruang Lingkup", [
            "Berlaku untuk seluruh LO yang dikirim dengan mobil tangki dari TBBM ke SPBU (COCO, CODO, DODO) dan pelanggan industri di semua regional.",
        ]),
        ("3. Komponen SLA", [
            "Jarak standar: jarak dari TBBM asal ke lokasi pelanggan, dalam kilometer, yang ditetapkan untuk setiap pelanggan dan tidak berubah dari bulan ke bulan.",
            "Kecepatan rujukan: 40 kilometer per jam untuk menghitung waktu tempuh.",
            "Waktu muat dan bongkar: 60 menit, sudah termasuk pemeriksaan dokumen dan pengisian tangki.",
        ]),
        ("4. Rumus SLA", [
            "SLA pengiriman (menit) = (jarak standar dalam km dibagi 40) dikali 60, ditambah 60 menit.",
            "Contoh: pelanggan dengan jarak standar 120 km. Waktu tempuh rujukan 120 dibagi 40 dikali 60 sama dengan 180 menit. SLA = 180 + 60 = 240 menit.",
        ]),
        ("5. Durasi dan Status", [
            "Durasi kirim: waktu sejak mobil tangki keluar dari TBBM sampai bongkar selesai, dalam menit.",
            "Terkirim: durasi kirim tidak melebihi SLA.",
            "Terlambat: durasi kirim melebihi SLA. Setiap LO terlambat wajib memiliki satu alasan dari daftar pada bagian 6.",
            "Dalam Perjalanan: LO yang belum selesai pada tanggal pelaporan. LO ini tidak dihitung dalam tingkat keterlambatan.",
        ]),
        ("6. Alasan Keterlambatan", [
            "Antrean muat di TBBM: LO menunggu giliran muat melebihi kapasitas slot.",
            "Kemacetan lalu lintas: waktu tempuh terganggu kepadatan jalan.",
            "Akses jalan rusak: jalan menuju lokasi pelanggan tidak dapat dilalui dengan kecepatan normal.",
            "Cuaca buruk: gelombang laut, hujan lebat, atau banjir yang menghambat perjalanan.",
            "Antrean bongkar di SPBU: mobil tangki menunggu giliran bongkar di SPBU atau pelanggan.",
            "Kerusakan mobil tangki: mobil tangki mogok atau harus diganti di tengah perjalanan.",
            "Pasokan dari terminal alternatif: LO dilayani TBBM cadangan sesuai SOP pengalihan pasokan.",
        ]),
        ("7. Pengecualian", [
            "Cuaca buruk tidak membebaskan LO dari SLA. Alasan dicatat dan dapat dijadikan dasar peninjauan rute, tetapi SLA tidak diubah secara otomatis.",
            "Penyesuaian SLA untuk pengalihan pasokan hanya berlaku bila ditetapkan oleh Regional Distribution Manager sesuai SOP pengalihan pasokan.",
        ]),
        ("8. Ambang dan Pemantauan", [
            "Tingkat keterlambatan dihitung sebagai jumlah LO terlambat dibagi jumlah LO yang selesai, dalam persen. Target nasional 15 persen.",
            "Pemantauan dan eskalasi mengikuti SOP penanganan keterlambatan (SOP-DIST-014).",
        ]),
        ("9. Tanggung Jawab", [
            "Terminal Manager: memastikan setiap LO terlambat memiliki satu alasan yang tercatat.",
            "Regional Distribution Manager: meninjau alasan terbanyak setiap bulan dan mengusulkan perbaikan rute.",
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
    for spec in (SOP_DELIVERY, SOP_QUOTA, SOP_OUTAGE, SOP_SLA):
        print(build(spec))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

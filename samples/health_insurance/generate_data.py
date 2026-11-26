#!/usr/bin/env python3
"""Generate synthetic claims of a private health insurer (Indonesia), with planted fraud patterns.

Tables (CSV in data/, see KONTRAK-DATA.md for every column):
  peserta.csv        insured members: product, segment, age group, province, hashed phone and bank account
  penyedia.csv       hospitals and clinics: class, partner status, province, city, coordinates
  dokter.csv         doctors: specialty, the provider they work at
  diagnosis.csv      the diagnosis codes used (a small common subset of ICD-10), with their group
  klaim.csv          one row per claim: member, provider, doctor, dates, service, diagnosis, length of stay, amounts, status
  premi_bulanan.csv  earned premium per month and product, for the claim ratio
  ground_truth.csv   which claims belong to a planted pattern (evaluation only: never loaded into the warehouse)

Deterministic (fixed seed): running it again writes identical files. Entirely synthetic: every provider is called "RS Demo ..." or
"Klinik Demo ...", doctors are codes, members are ids, phones and bank accounts are hashes of made-up numbers.

Planted patterns (the script prints how each came out):
  * upcoding        RS Demo Cendana Bekasi bills about 40% more than peers of its class for the same diagnosis, admits some simple
                    cases (diarrhoea, upper respiratory infection, fever) that peers treat as outpatients, and codes dengue fever as
                    the more severe dengue haemorrhagic fever.
  * jaringan        From June 2026, about 70 members claim reimbursement for outpatient visits at Klinik Demo Melati Jakarta Timur,
                    all with one doctor, mostly at weekends and in the evening, for 2.2-2.9 million each (about seven times a normal
                    visit). Their reimbursements go to 6 bank accounts and they share 10 phone numbers.
  * volume_dokter   From May 2026 one internist at RS Demo Kenanga Surabaya records 40-65 extra hypertension and diabetes control
                    visits every working day. The data holds only this insurer's members, so a doctor normally has a handful of
                    them on a busy day; this one has around 50-70.
  * lama_rawat      RS Demo Flamboyan Medan keeps appendicitis, gallstone, pneumonia and typhoid patients 3-5 days longer than
                    peers, and bills for every extra day.
  * klaim_ganda     About 350 claims are a second claim for the same member, date and diagnosis at another provider in the same
                    city, filed later as a reimbursement.
  * rawat_ulang     About a fifth of the inpatient stays at RS Demo Tanjung Makassar are followed by a readmission for the same
                    diagnosis 2-6 days after discharge.
  * wabah (legitimate, not fraud)  January-March 2026: dengue claims are 3.5 times the usual level in DKI Jakarta, Jawa Barat,
                    Banten and Jawa Tengah, spread over all providers there in proportion to their size.
Seasonality: dengue peaks in the rainy months (November-April). The portfolio grows: members join from 2023 to September 2026.

Usage: python samples/health_insurance/generate_data.py [--claims 400000] [--members 120000]
"""
from __future__ import annotations

import argparse
import bisect
import csv
import hashlib
import math
import random
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

OUT = Path(__file__).resolve().parent / "data"
SEED = 2026
START, END = date(2025, 1, 1), date(2026, 11, 25)
CLAIMS, MEMBERS = 400_000, 120_000

# city -> (province as the map knows it, latitude, longitude, weight of members and providers)
CITIES = {
    "Jakarta Selatan": ("DKI Jakarta", -6.26, 106.81, 9), "Jakarta Timur": ("DKI Jakarta", -6.23, 106.90, 8),
    "Jakarta Pusat": ("DKI Jakarta", -6.18, 106.83, 5), "Jakarta Barat": ("DKI Jakarta", -6.17, 106.76, 7),
    "Jakarta Utara": ("DKI Jakarta", -6.13, 106.88, 5), "Bekasi": ("Jawa Barat", -6.24, 107.00, 8),
    "Bandung": ("Jawa Barat", -6.91, 107.61, 8), "Bogor": ("Jawa Barat", -6.60, 106.80, 5), "Depok": ("Jawa Barat", -6.40, 106.82, 5),
    "Cirebon": ("Jawa Barat", -6.73, 108.55, 2), "Tangerang": ("Banten", -6.18, 106.63, 7), "Serang": ("Banten", -6.12, 106.15, 2),
    "Semarang": ("Jawa Tengah", -6.97, 110.42, 5), "Surakarta": ("Jawa Tengah", -7.57, 110.82, 3),
    "Yogyakarta": ("DI Yogyakarta", -7.80, 110.36, 3), "Surabaya": ("Jawa Timur", -7.25, 112.75, 8), "Malang": ("Jawa Timur", -7.98, 112.63, 3),
    "Denpasar": ("Bali", -8.65, 115.22, 3), "Medan": ("Sumatera Utara", 3.59, 98.67, 6), "Palembang": ("Sumatera Selatan", -2.98, 104.75, 3),
    "Pekanbaru": ("Riau", 0.51, 101.45, 3), "Padang": ("Sumatera Barat", -0.95, 100.35, 2), "Bandar Lampung": ("Lampung", -5.43, 105.26, 2),
    "Batam": ("Kepulauan Riau", 1.13, 104.05, 2), "Pontianak": ("Kalimantan Barat", -0.03, 109.33, 1),
    "Banjarmasin": ("Kalimantan Selatan", -3.32, 114.59, 1), "Balikpapan": ("Kalimantan Timur", -1.24, 116.85, 2),
    "Makassar": ("Sulawesi Selatan", -5.15, 119.43, 3), "Manado": ("Sulawesi Utara", 1.47, 124.84, 1),
}
DENGUE_OUTBREAK = {"DKI Jakarta", "Jawa Barat", "Banten", "Jawa Tengah"}

SPECIALTIES = ["Umum", "Sp.PD (Penyakit Dalam)", "Sp.A (Anak)", "Sp.OG (Kebidanan dan Kandungan)", "Sp.B (Bedah)",
               "Sp.JP (Jantung)", "Sp.N (Saraf)", "Sp.P (Paru)", "Sp.M (Mata)", "Sp.KK (Kulit dan Kelamin)", "Sp.OT (Ortopedi)"]

# code -> (name, group, weight, inpatient share, outpatient cost, inpatient cost of a typical stay, typical days, specialty, main procedure)
DIAGNOSES = {
    "A09": ("Diare dan gastroenteritis", "Infeksi", 7.0, 0.25, 350_000, 6_500_000, 3, "Sp.PD (Penyakit Dalam)", "Rawat inap konservatif"),
    "A90": ("Demam dengue", "Infeksi", 3.0, 0.45, 400_000, 8_000_000, 4, "Sp.PD (Penyakit Dalam)", "Rawat inap konservatif"),
    "A91": ("Demam berdarah dengue", "Infeksi", 2.0, 0.85, 500_000, 12_000_000, 5, "Sp.PD (Penyakit Dalam)", "Rawat inap konservatif"),
    "A01.0": ("Demam tifoid", "Infeksi", 3.0, 0.50, 400_000, 9_000_000, 5, "Sp.PD (Penyakit Dalam)", "Rawat inap konservatif"),
    "B34.9": ("Infeksi virus", "Infeksi", 4.0, 0.05, 300_000, 5_000_000, 2, "Umum", "Rawat inap konservatif"),
    "J06.9": ("Infeksi saluran pernapasan atas akut", "Pernapasan", 14.0, 0.02, 300_000, 5_000_000, 2, "Umum", "Rawat inap konservatif"),
    "J18.9": ("Pneumonia", "Pernapasan", 3.0, 0.75, 550_000, 18_000_000, 6, "Sp.P (Paru)", "Rawat inap konservatif"),
    "J45.9": ("Asma", "Pernapasan", 3.0, 0.10, 450_000, 7_000_000, 3, "Sp.P (Paru)", "Rawat inap konservatif"),
    "I10": ("Hipertensi esensial", "Kardiovaskular", 9.0, 0.03, 450_000, 8_000_000, 3, "Sp.PD (Penyakit Dalam)", "Rawat inap konservatif"),
    "I21.9": ("Infark miokard akut", "Kardiovaskular", 0.6, 1.00, 0, 85_000_000, 6, "Sp.JP (Jantung)", "Kateterisasi jantung dan pemasangan stent"),
    "I63.9": ("Stroke iskemik", "Kardiovaskular", 0.7, 1.00, 0, 45_000_000, 7, "Sp.N (Saraf)", "Rawat inap stroke"),
    "E11.9": ("Diabetes melitus tipe 2", "Metabolik", 7.0, 0.04, 500_000, 10_000_000, 4, "Sp.PD (Penyakit Dalam)", "Rawat inap konservatif"),
    "K29.7": ("Gastritis", "Pencernaan", 6.0, 0.05, 320_000, 5_500_000, 3, "Umum", "Rawat inap konservatif"),
    "K35.8": ("Apendisitis akut", "Bedah", 1.2, 1.00, 0, 28_000_000, 3, "Sp.B (Bedah)", "Apendektomi"),
    "K80.2": ("Batu empedu (kolelitiasis)", "Bedah", 0.5, 0.90, 900_000, 38_000_000, 4, "Sp.B (Bedah)", "Kolesistektomi laparoskopi"),
    "N39.0": ("Infeksi saluran kemih", "Infeksi", 3.0, 0.10, 380_000, 6_000_000, 3, "Sp.PD (Penyakit Dalam)", "Rawat inap konservatif"),
    "O80": ("Persalinan normal", "Kehamilan", 1.2, 1.00, 0, 9_000_000, 2, "Sp.OG (Kebidanan dan Kandungan)", "Persalinan normal"),
    "O82": ("Persalinan sesar", "Kehamilan", 1.0, 1.00, 0, 32_000_000, 3, "Sp.OG (Kebidanan dan Kandungan)", "Seksio sesarea"),
    "M54.5": ("Nyeri punggung bawah", "Muskuloskeletal", 4.0, 0.02, 420_000, 6_000_000, 2, "Sp.N (Saraf)", "Rawat inap konservatif"),
    "S52.5": ("Patah tulang pergelangan tangan", "Cedera", 0.6, 0.70, 900_000, 30_000_000, 3, "Sp.OT (Ortopedi)", "Reposisi dan fiksasi fraktur"),
    "H10.9": ("Konjungtivitis", "Mata", 2.0, 0.00, 280_000, 0, 0, "Sp.M (Mata)", ""),
    "L30.9": ("Dermatitis", "Kulit", 3.0, 0.00, 300_000, 0, 0, "Sp.KK (Kulit dan Kelamin)", ""),
    "N18.5": ("Penyakit ginjal kronis stadium 5", "Ginjal", 0.5, 0.15, 1_300_000, 25_000_000, 5, "Sp.PD (Penyakit Dalam)", "Hemodialisis"),
    "C50.9": ("Kanker payudara", "Onkologi", 0.3, 0.35, 9_000_000, 55_000_000, 5, "Sp.B (Bedah)", "Kemoterapi"),
    "R50.9": ("Demam, tidak spesifik", "Gejala umum", 5.0, 0.05, 300_000, 5_000_000, 2, "Umum", "Rawat inap konservatif"),
    "Z00.0": ("Pemeriksaan kesehatan umum", "Pemeriksaan", 2.0, 0.00, 450_000, 0, 0, "Umum", ""),
}
DENGUE = ("A90", "A91")
OUTPATIENT_PROCEDURE = {"N18.5": "Hemodialisis", "C50.9": "Kemoterapi"}

# product -> (segment, share of members, base monthly premium IDR before the age factor, annual limit IDR, how much its members use care)
PRODUCTS = {
    "Sehat Silver": ("Individu", 22, 450_000, 150_000_000, 0.9), "Sehat Gold": ("Individu", 14, 750_000, 300_000_000, 1.3),
    "Sehat Platinum": ("Individu", 6, 1_200_000, 1_000_000_000, 1.9), "Kumpulan Standar": ("Korporat", 40, 350_000, 100_000_000, 0.75),
    "Kumpulan Eksekutif": ("Korporat", 18, 650_000, 400_000_000, 1.25),
}
AGE_GROUPS = {"0-17": (18, 0.9, 0.7), "18-30": (24, 0.7, 0.8), "31-45": (28, 1.0, 1.0), "46-60": (21, 1.5, 1.6), "60+": (9, 2.3, 2.6)}
# age group -> (share, claim frequency factor, premium factor)

CLASS_FACTOR = {"A": 1.45, "B": 1.2, "C": 1.0, "D": 0.85, "Utama": 0.9, "Pratama": 0.7}
CLASS_SIZE = {"A": 9, "B": 6, "C": 4, "D": 2, "Utama": 1.5, "Pratama": 1}
WORDS = ["Anggrek", "Mawar", "Cempaka", "Teratai", "Seroja", "Kamboja", "Dahlia", "Bougenvil", "Asoka", "Nusa Indah", "Meranti",
         "Jati", "Mahoni", "Beringin", "Akasia", "Kemuning", "Gardenia", "Lili", "Tulip", "Sakura", "Matahari", "Kenari", "Pinus",
         "Cemara", "Bambu", "Palem", "Rasamala", "Damar", "Ketapang", "Trembesi", "Kelapa", "Pandan", "Sirih", "Rosela", "Lavender"]
REJECTIONS = {"Dokumen tidak lengkap": 40, "Masa tunggu belum terpenuhi": 20, "Melebihi limit tahunan": 15, "Di luar pertanggungan": 25}

PLANTED = {  # pattern -> (provider name, city, kind, class, partner)
    "upcoding": ("RS Demo Cendana Bekasi", "Bekasi", "Rumah Sakit", "B", "Rekanan"),
    "jaringan": ("Klinik Demo Melati Jakarta Timur", "Jakarta Timur", "Klinik", "Utama", "Non-rekanan"),
    "volume_dokter": ("RS Demo Kenanga Surabaya", "Surabaya", "Rumah Sakit", "B", "Rekanan"),
    "lama_rawat": ("RS Demo Flamboyan Medan", "Medan", "Rumah Sakit", "C", "Rekanan"),
    "rawat_ulang": ("RS Demo Tanjung Makassar", "Makassar", "Rumah Sakit", "B", "Rekanan"),
}


def token(prefix: str, value: str) -> str:
    """A stable pseudonym for a made-up number, so shared ones can be counted without showing any number."""
    return f"{prefix}-{hashlib.sha256(value.encode()).hexdigest()[:10].upper()}"


class Picker:
    """Weighted choice in O(log n), deterministic for one random stream."""

    def __init__(self, items: list, weights: list[float]) -> None:
        self.items = items
        self.cum = []
        total = 0.0
        for w in weights:
            total += w
            self.cum.append(total)
        self.total = total

    def __call__(self, rnd: random.Random):
        return self.items[bisect.bisect_right(self.cum, rnd.random() * self.total)]


def build_providers(rnd: random.Random):
    providers, words = [], iter(w for w in WORDS)
    n = 0

    def add(name, city, kind, klass, partner):
        nonlocal n
        n += 1
        prov, lat, lon, _ = CITIES[city]
        providers.append({
            "kode_penyedia": f"PRV-{n:04d}", "nama_penyedia": name, "tipe_penyedia": kind, "kelas": klass, "status_rekanan": partner,
            "provinsi": prov, "kota": city, "latitude": round(lat + rnd.uniform(-0.05, 0.05), 5), "longitude": round(lon + rnd.uniform(-0.05, 0.05), 5),
        })

    for name, city, kind, klass, partner in PLANTED.values():
        add(name, city, kind, klass, partner)
    used = {(v[1], v[0].split(" Demo ")[1].split(" ")[0]) for v in PLANTED.values()}
    for city, (_, _, _, weight) in CITIES.items():
        hospitals, clinics = max(1, round(weight * 0.9)), max(1, round(weight * 0.6))
        for kind, count in (("Rumah Sakit", hospitals), ("Klinik", clinics)):
            for _ in range(count):
                word = next(words, None)
                if word is None:
                    words = iter(WORDS)
                    word = next(words)
                while (city, word) in used:
                    word = next(words, None) or WORDS[rnd.randrange(len(WORDS))]
                used.add((city, word))
                klass = rnd.choices(["A", "B", "C", "D"], [8, 30, 45, 17])[0] if kind == "Rumah Sakit" else rnd.choices(["Utama", "Pratama"], [40, 60])[0]
                partner = "Rekanan" if rnd.random() < 0.85 else "Non-rekanan"
                add(f"{'RS' if kind == 'Rumah Sakit' else 'Klinik'} Demo {word} {city}", city, kind, klass, partner)
    return providers


def build_doctors(rnd: random.Random, providers: list[dict]):
    doctors, n = [], 0
    for p in providers:
        size = CLASS_SIZE[p["kelas"]]
        count = int(size * rnd.uniform(3, 5)) if p["tipe_penyedia"] == "Rumah Sakit" else rnd.randint(3, 6)
        specs = ["Umum"] * max(2, count // 4)
        if p["tipe_penyedia"] == "Rumah Sakit":
            specs += SPECIALTIES[1:] * max(1, count // 12)
        else:
            specs += rnd.sample(["Sp.PD (Penyakit Dalam)", "Sp.A (Anak)", "Sp.KK (Kulit dan Kelamin)", "Sp.M (Mata)"], 2)
        for spec in specs:
            n += 1
            doctors.append({"kode_dokter": f"DR-{n:05d}", "nama_dokter": f"dr. Demo {n:05d}", "spesialisasi": spec, "kode_penyedia": p["kode_penyedia"]})
    return doctors


def build_members(rnd: random.Random, count: int):
    city_pick = Picker(list(CITIES), [c[3] for c in CITIES.values()])
    product_pick = Picker(list(PRODUCTS), [p[1] for p in PRODUCTS.values()])
    age_pick = Picker(list(AGE_GROUPS), [a[0] for a in AGE_GROUPS.values()])
    companies = [f"PT Demo {w} {s}" for w, s in zip(WORDS, ["Abadi", "Sejahtera", "Mandiri", "Prima", "Nusantara", "Makmur", "Utama", "Jaya"] * 5)][:30]
    members = []
    for i in range(1, count + 1):
        product = product_pick(rnd)
        segment = PRODUCTS[product][0]
        city = city_pick(rnd)
        start = date(2023, 1, 1) + timedelta(days=int((date(2026, 9, 30) - date(2023, 1, 1)).days * rnd.random() ** 0.8))
        ended = rnd.random() < 0.08
        members.append({
            "id_peserta": f"PST-{i:07d}", "id_polis": f"POL-{(i if segment == 'Individu' else 900000 + rnd.randrange(30)):07d}",
            "produk": product, "segmen": segment, "pemegang_polis": rnd.choice(companies) if segment == "Korporat" else "",
            "jenis_kelamin": rnd.choice(["Laki-laki", "Perempuan"]), "kelompok_usia": age_pick(rnd), "provinsi": CITIES[city][0], "kota": city,
            "tanggal_mulai": start.isoformat(), "status_polis": "Berakhir" if ended else "Aktif",
            "telepon_hash": token("TEL", f"phone-{i}"), "rekening_hash": token("REK", f"account-{i}"),
        })
    return members


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--claims", type=int, default=CLAIMS)
    parser.add_argument("--members", type=int, default=MEMBERS)
    args = parser.parse_args(argv)

    rnd = random.Random(SEED)
    providers = build_providers(random.Random(SEED + 1))
    doctors = build_doctors(random.Random(SEED + 2), providers)
    members = build_members(random.Random(SEED + 3), args.members)
    by_name = {p["nama_penyedia"]: p for p in providers}
    planted_code = {k: by_name[v[0]]["kode_penyedia"] for k, v in PLANTED.items()}

    docs_by_provider: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    for d in doctors:
        docs_by_provider[d["kode_penyedia"]][d["spesialisasi"]].append(d["kode_dokter"])
    hospitals_by_city, all_by_city = defaultdict(list), defaultdict(list)
    for p in providers:
        all_by_city[p["kota"]].append(p)
        if p["tipe_penyedia"] == "Rumah Sakit":
            hospitals_by_city[p["kota"]].append(p)
    pick_hospital = {c: Picker(v, [CLASS_SIZE[p["kelas"]] for p in v]) for c, v in hospitals_by_city.items()}
    pick_any = {c: Picker(v, [CLASS_SIZE[p["kelas"]] * (1.6 if p["tipe_penyedia"] == "Klinik" else 1) for p in v]) for c, v in all_by_city.items()}
    city_names = list(CITIES)

    def diag_picker(month: int, outbreak: bool) -> Picker:
        weights = []
        for code, d in DIAGNOSES.items():
            w = d[2]
            if code in DENGUE:
                w *= 1.8 if month in (1, 2, 3, 4) else 1.3 if month in (11, 12) else 0.5
                w *= 3.5 if outbreak else 1
            weights.append(w)
        return Picker(list(DIAGNOSES), weights)

    diag_pickers = {(m, o): diag_picker(m, o) for m in range(1, 13) for o in (False, True)}
    member_pick = Picker(members, [AGE_GROUPS[m["kelompok_usia"]][1] * PRODUCTS[m["produk"]][4] * rnd.lognormvariate(0, 0.6) for m in members])

    def doctor_for(provider: dict, specialty: str) -> str:
        pool = docs_by_provider[provider["kode_penyedia"]]
        return rnd.choice(pool.get(specialty) or pool.get("Umum") or next(iter(pool.values())))

    claims: list[dict] = []
    truth: dict[str, str] = {}

    def add_claim(member: dict, provider: dict, doctor: str, admit: date, service: str, code: str, los: int, billed: int,
                  method: str, hour: int, pattern: str = "", filed_after: int | None = None) -> dict:
        discharge = admit + timedelta(days=los)
        filed = discharge + timedelta(days=filed_after if filed_after is not None else (rnd.randint(0, 2) if method == "Cashless" else rnd.randint(3, 25)))
        decided = filed + timedelta(days=rnd.randint(1, 4) if method == "Cashless" else rnd.randint(3, 12) + (3 if billed > 30_000_000 else 0))
        claim = {
            "id_klaim": f"KLM-{len(claims) + 1:07d}", "id_peserta": member["id_peserta"], "kode_penyedia": provider["kode_penyedia"],
            "kode_dokter": doctor, "tanggal_masuk": admit.isoformat(), "tanggal_keluar": discharge.isoformat(), "jam_kunjungan": hour,
            "tanggal_pengajuan": filed.isoformat(), "tanggal_keputusan": "", "jenis_layanan": service, "kode_diagnosis": code,
            "tindakan_utama": DIAGNOSES[code][8] if service == "Rawat Inap" else OUTPATIENT_PROCEDURE.get(code, "Konsultasi dan pengobatan"),
            "lama_rawat_hari": los, "jumlah_tagihan_idr": billed, "jumlah_disetujui_idr": 0, "jumlah_dibayar_idr": 0,
            "metode_klaim": method, "rekening_penggantian_hash": member["rekening_hash"] if method == "Reimbursement" else "",
            "status_klaim": "Diproses", "alasan_penolakan": "",
        }
        if decided <= END:
            claim["tanggal_keputusan"] = decided.isoformat()
            reject = (0.55 if code == "Z00.0" else 0.04) if not pattern else 0.03
            if rnd.random() < reject:
                claim["status_klaim"] = "Ditolak"
                claim["alasan_penolakan"] = "Di luar pertanggungan" if code == "Z00.0" else rnd.choices(list(REJECTIONS), list(REJECTIONS.values()))[0]
            else:
                approved = int(billed * (rnd.uniform(0.9, 1.0) if method == "Cashless" else rnd.uniform(0.86, 1.0)) / 1000) * 1000
                claim.update(status_klaim="Dibayar", jumlah_disetujui_idr=approved, jumlah_dibayar_idr=approved)
        claims.append(claim)
        if pattern:
            truth[claim["id_klaim"]] = pattern
        return claim

    def cost(code: str, provider: dict, service: str, los: int) -> int:
        d = DIAGNOSES[code]
        factor = CLASS_FACTOR[provider["kelas"]] * rnd.lognormvariate(0, 0.28)
        if service == "Rawat Inap":
            value = d[5] * factor * (0.55 + 0.45 * los / max(d[6], 1))
        else:
            value = (d[4] or 400_000) * factor * (1.8 if service == "Gawat Darurat" else 1)
        if provider["kode_penyedia"] == planted_code["upcoding"]:
            value *= 1.4
        return int(round(value, -3))

    days = (END - START).days
    for _ in range(args.claims):
        member = member_pick(rnd)
        first = max(START, date.fromisoformat(member["tanggal_mulai"]))
        if first > END:
            continue
        admit = first + timedelta(days=rnd.randrange((END - first).days + 1))
        outbreak = admit.year == 2026 and admit.month <= 3 and member["provinsi"] in DENGUE_OUTBREAK
        code = diag_pickers[(admit.month, outbreak)](rnd)
        d = DIAGNOSES[code]
        if code in ("O80", "O82") and (member["jenis_kelamin"] != "Perempuan" or member["kelompok_usia"] not in ("18-30", "31-45")):
            code, d = "J06.9", DIAGNOSES["J06.9"]
        inpatient = rnd.random() < d[3]
        city = member["kota"] if rnd.random() < 0.88 else rnd.choice(city_names)
        provider = (pick_hospital if inpatient else pick_any)[city](rnd)
        pattern = ""
        if provider["kode_penyedia"] == planted_code["upcoding"]:
            pattern = "upcoding"
            if not inpatient and code in ("A09", "J06.9", "R50.9") and rnd.random() < 0.12:
                inpatient = True
            if code == "A90" and rnd.random() < 0.6:
                code, d = "A91", DIAGNOSES["A91"]
        service = "Rawat Inap" if inpatient else ("Gawat Darurat" if rnd.random() < 0.06 else "Rawat Jalan")
        los = max(1, round(rnd.gauss(d[6] or 2, max(1.0, (d[6] or 2) * 0.3)))) if inpatient else 0
        if inpatient and provider["kode_penyedia"] == planted_code["lama_rawat"] and code in ("K35.8", "K80.2", "J18.9", "A01.0"):
            los += rnd.randint(3, 5)
            pattern = "lama_rawat"
        specialty = d[7] if (inpatient or rnd.random() < 0.45) else "Umum"
        if member["kelompok_usia"] == "0-17" and specialty in ("Umum", "Sp.PD (Penyakit Dalam)"):
            specialty = "Sp.A (Anak)"
        doctor = doctor_for(provider, specialty)
        partner = provider["status_rekanan"] == "Rekanan"
        method = "Cashless" if partner and rnd.random() < (0.92 if inpatient else 0.62) else "Reimbursement"
        hour = rnd.randint(0, 23) if service != "Rawat Jalan" else min(21, max(7, int(rnd.gauss(13, 3.2))))
        claim = add_claim(member, provider, doctor, admit, service, code, los, cost(code, provider, service, los), method, hour, pattern)

        if inpatient and provider["kode_penyedia"] == planted_code["rawat_ulang"] and rnd.random() < 0.22:
            back = date.fromisoformat(claim["tanggal_keluar"]) + timedelta(days=rnd.randint(2, 6))
            if back <= END:
                los2 = rnd.randint(2, 4)
                add_claim(member, provider, doctor_for(provider, d[7]), back, "Rawat Inap", code, los2,
                          int(round(cost(code, provider, "Rawat Inap", los2) * 0.6, -3)), method, rnd.randint(0, 23), "rawat_ulang")

    # klaim_ganda: the same visit claimed again at another provider in the same city, later, as a reimbursement.
    candidates = [c for c in claims if not truth.get(c["id_klaim"]) and c["jenis_layanan"] != "Gawat Darurat"]
    member_by_id = {m["id_peserta"]: m for m in members}
    for original in rnd.sample(candidates, 350):
        member = member_by_id[original["id_peserta"]]
        others = [p for p in all_by_city[member["kota"]] if p["kode_penyedia"] != original["kode_penyedia"] and p["kode_penyedia"] not in planted_code.values()]
        if not others:
            continue
        provider = rnd.choice(others)
        admit = date.fromisoformat(original["tanggal_masuk"])
        add_claim(member, provider, doctor_for(provider, DIAGNOSES[original["kode_diagnosis"]][7]), admit, original["jenis_layanan"],
                  original["kode_diagnosis"], int(original["lama_rawat_hari"]), int(round(int(original["jumlah_tagihan_idr"]) * rnd.uniform(0.95, 1.05), -3)),
                  "Reimbursement", int(original["jam_kunjungan"]), "klaim_ganda", filed_after=rnd.randint(10, 30))

    # jaringan: a group of members, one clinic, one doctor, shared phones and bank accounts.
    melati = by_name[PLANTED["jaringan"][0]]
    ring_doctor = docs_by_provider[melati["kode_penyedia"]]["Umum"][0]
    jakarta = [m for m in members if m["provinsi"] == "DKI Jakarta" and m["segmen"] == "Individu" and m["tanggal_mulai"] < "2026-05-01"]
    ring = rnd.sample(jakarta, 70)
    accounts = [token("REK", f"ring-account-{i}") for i in range(6)]
    phones = [token("TEL", f"ring-phone-{i}") for i in range(10)]
    for i, member in enumerate(ring):
        member["rekening_hash"] = accounts[i % 6]
        member["telepon_hash"] = phones[i % 10]
    ring_start = date(2026, 6, 1)
    ring_days = [ring_start + timedelta(days=k) for k in range((END - ring_start).days + 1)]
    weekend = [d for d in ring_days if d.weekday() >= 5]
    for member in ring:
        for _ in range(rnd.randint(4, 9)):
            admit = rnd.choice(weekend) if rnd.random() < 0.7 else rnd.choice(ring_days)
            code = rnd.choice(["R50.9", "J06.9", "M54.5", "K29.7", "B34.9"])
            add_claim(member, melati, ring_doctor, admit, "Rawat Jalan", code, 0, rnd.randrange(2_200, 2_950) * 1000, "Reimbursement",
                      rnd.randint(18, 23), "jaringan")

    # volume_dokter: an internist with an impossible number of control visits a day.
    kenanga = by_name[PLANTED["volume_dokter"][0]]
    busy_doctor = docs_by_provider[kenanga["kode_penyedia"]]["Sp.PD (Penyakit Dalam)"][0]
    east_java = [m for m in members if m["provinsi"] == "Jawa Timur" and m["tanggal_mulai"] < "2026-04-01"]
    day = date(2026, 5, 1)
    while day <= END:
        if day.weekday() < 5:
            for _ in range(rnd.randint(40, 65)):
                code = rnd.choice(["I10", "E11.9"])
                add_claim(rnd.choice(east_java), kenanga, busy_doctor, day, "Rawat Jalan", code, 0, rnd.randrange(380, 520) * 1000, "Cashless",
                          rnd.randint(8, 21), "volume_dokter")
        day += timedelta(days=1)

    claims.sort(key=lambda c: (c["tanggal_masuk"], c["id_klaim"]))

    # Earned premium per month and product: active members x monthly rate x age factor, scaled so the portfolio claim ratio is about 72%.
    monthly: dict[tuple[str, str], list[float]] = defaultdict(lambda: [0, 0.0])
    month = date(START.year, START.month, 1)
    starts = sorted((m["tanggal_mulai"], m["produk"], AGE_GROUPS[m["kelompok_usia"]][2]) for m in members)
    while month <= END:
        key = month.isoformat()
        cut = (month + timedelta(days=32)).replace(day=1).isoformat()
        for started, product, age_factor in starts:
            if started >= cut:
                break
            monthly[(key, product)][0] += 1
            monthly[(key, product)][1] += PRODUCTS[product][2] * age_factor
        month = (month + timedelta(days=32)).replace(day=1)
    paid = sum(c["jumlah_dibayar_idr"] for c in claims)
    scale = paid / (0.72 * sum(v[1] for v in monthly.values()))
    premiums = [
        {"bulan": k[0], "produk": k[1], "segmen": PRODUCTS[k[1]][0], "jumlah_peserta_aktif": int(v[0]), "premi_idr": int(round(v[1] * scale, -3))}
        for k, v in sorted(monthly.items())
    ]

    OUT.mkdir(parents=True, exist_ok=True)

    def write(name: str, rows: list[dict]) -> None:
        with (OUT / name).open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)

    write("peserta.csv", members)
    write("penyedia.csv", providers)
    write("dokter.csv", doctors)
    write("diagnosis.csv", [{"kode_diagnosis": k, "nama_diagnosis": v[0], "kelompok_diagnosis": v[1]} for k, v in DIAGNOSES.items()])
    write("klaim.csv", claims)
    write("premi_bulanan.csv", premiums)
    write("ground_truth.csv", [{"id_klaim": k, "pola": v} for k, v in sorted(truth.items())])

    report(claims, providers, doctors, members, premiums, truth, planted_code)
    return 0


def report(claims, providers, doctors, members, premiums, truth, planted_code) -> None:
    """How each planted pattern came out, so a reader can check it against the questions."""
    paid = sum(c["jumlah_dibayar_idr"] for c in claims)
    print(f"members {len(members):,}  providers {len(providers):,}  doctors {len(doctors):,}  claims {len(claims):,}  "
          f"paid IDR {paid:,}  claim ratio {paid / sum(p['premi_idr'] for p in premiums):.1%}")
    print("planted claims:", dict(Counter(truth.values())))
    print("status:", dict(Counter(c["status_klaim"] for c in claims)))

    def avg(rows, field):
        return sum(int(r[field]) for r in rows) / len(rows) if rows else 0

    peers_b = [c for c in claims if c["kode_penyedia"] != planted_code["upcoding"] and c["jenis_layanan"] == "Rawat Inap"]
    klass = {p["kode_penyedia"]: p["kelas"] for p in providers}
    peers_b = [c for c in peers_b if klass[c["kode_penyedia"]] == "B"]
    cendana = [c for c in claims if c["kode_penyedia"] == planted_code["upcoding"] and c["jenis_layanan"] == "Rawat Inap"]
    print(f"upcoding: inpatient bill per case at Cendana {avg(cendana, 'jumlah_tagihan_idr'):,.0f} vs class B peers {avg(peers_b, 'jumlah_tagihan_idr'):,.0f}")
    for code in ("A91", "J18.9", "A01.0", "O82"):
        mine = [c for c in cendana if c["kode_diagnosis"] == code]
        theirs = [c for c in peers_b if c["kode_diagnosis"] == code]
        print(f"   {code}: Cendana {avg(mine, 'jumlah_tagihan_idr'):,.0f} ({len(mine)}) vs class B peers {avg(theirs, 'jumlah_tagihan_idr'):,.0f} "
              f"= {avg(mine, 'jumlah_tagihan_idr') / avg(theirs, 'jumlah_tagihan_idr') - 1:+.0%}")
    ring = [c for c in claims if truth.get(c["id_klaim"]) == "jaringan"]
    print(f"jaringan: {len(ring)} claims, paid {sum(c['jumlah_dibayar_idr'] for c in ring):,}, accounts {len({c['rekening_penggantian_hash'] for c in ring})}")
    per_day = Counter((c["kode_dokter"], c["tanggal_masuk"]) for c in claims if c["jenis_layanan"] == "Rawat Jalan")
    top = per_day.most_common(1)[0]
    normal = sorted(per_day.values())[len(per_day) // 2]
    print(f"volume_dokter: busiest doctor-day {top[0]} with {top[1]} visits; median doctor-day {normal}")
    flam = [c for c in claims if c["kode_penyedia"] == planted_code["lama_rawat"] and c["kode_diagnosis"] == "K35.8"]
    others = [c for c in claims if c["kode_penyedia"] != planted_code["lama_rawat"] and c["kode_diagnosis"] == "K35.8"]
    print(f"lama_rawat: appendicitis days at Flamboyan {avg(flam, 'lama_rawat_hari'):.1f} vs others {avg(others, 'lama_rawat_hari'):.1f}")
    dengue = Counter((c["tanggal_masuk"][:7]) for c in claims if c["kode_diagnosis"] in DENGUE)
    print("dengue claims by month:", {k: dengue[k] for k in sorted(dengue) if k >= "2025-11" and k <= "2026-05"})


if __name__ == "__main__":
    raise SystemExit(main())

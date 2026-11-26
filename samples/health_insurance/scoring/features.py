"""The features of a claim, computed only from what is known when it arrives (the claims before it), so the history and the live
stream are scored the same way. Standard library only: the scoring service runs without installing anything.

A Context is fed claims in time order. For each claim it returns the feature values and the facts behind them (for the reasons
shown to an investigator), then remembers the claim.
"""
from __future__ import annotations

import math
from collections import defaultdict
from datetime import date, timedelta

FEATURES = [
    "biaya_vs_wajar",          # log of the bill over the usual bill for this diagnosis, service and provider class (above it only)
    "lama_rawat_vs_wajar",     # inpatient days over the usual days for this diagnosis, above it only (0 for outpatients)
    "indeks_biaya_penyedia",   # log of the provider's average bill ratio so far (a provider that bills high on every case)
    "peserta_per_rekening",    # log of how many members' reimbursements went to this bank account so far
    "peserta_per_telepon",     # log of how many members share this phone number
    "klaim_dokter_hari_itu",   # log of this doctor's claims on this day so far
    "klaim_dokter_per_hari",   # log of this doctor's average claims per working day over the last 30 days
    "indeks_lama_rawat_penyedia",  # the provider's average stay above the usual one so far (a provider that keeps every patient longer)
    "klaim_ganda",             # 1 when the member already claimed this diagnosis on this date at another provider
    "rawat_ulang_7_hari",      # 1 when the member left hospital for this diagnosis 0-7 days before this admission
]


def _date(value: str) -> date:
    return date.fromisoformat(value)


class Context:
    def __init__(self, usual_cost: dict[str, float], usual_days: dict[str, float], members: dict[str, dict], providers: dict[str, dict]) -> None:
        self.usual_cost = usual_cost      # "diagnosis|service|class" -> typical bill
        self.usual_days = usual_days      # diagnosis -> typical inpatient days
        self.members = members            # id_peserta -> {"telepon_hash": ...}
        self.providers = providers        # kode_penyedia -> {"kelas": ..., "status_rekanan": ...}
        self.account_members: dict[str, set[str]] = defaultdict(set)
        self.phone_members: dict[str, set[str]] = defaultdict(set)
        for member_id, member in members.items():
            self.phone_members[member.get("telepon_hash", "")].add(member_id)
        self.doctor_day: dict[tuple[str, str], int] = defaultdict(int)
        self.visits: dict[tuple[str, str, str], set[str]] = defaultdict(set)
        self.last_discharge: dict[tuple[str, str], date] = {}
        self.provider_ratio: dict[str, list[float]] = defaultdict(lambda: [0.0, 0])
        self.provider_stay: dict[str, list[float]] = defaultdict(lambda: [0.0, 0])
        self.doctor_days: dict[str, dict[str, int]] = defaultdict(dict)  # doctor -> date -> claims, last 30 days kept

    def usual(self, claim: dict) -> float:
        klass = self.providers.get(claim["kode_penyedia"], {}).get("kelas", "C")
        key = f"{claim['kode_diagnosis']}|{claim['jenis_layanan']}|{klass}"
        return (self.usual_cost.get(key) or self.usual_cost.get(f"{claim['kode_diagnosis']}|{claim['jenis_layanan']}|*")
                or self.usual_cost.get(f"{claim['kode_diagnosis']}|*|*") or self.usual_cost["*|*|*"])

    def features(self, claim: dict) -> tuple[list[float], dict]:
        """Feature values and the facts behind them, for a claim not yet remembered."""
        bill = float(claim["jumlah_tagihan_idr"] or 0)
        ratio = min(max(max(bill, 1.0) / self.usual(claim), 0.1), 20.0)  # a bill 20 times the usual says all there is to say
        days = int(claim.get("lama_rawat_hari") or 0)
        usual_days = self.usual_days.get(claim["kode_diagnosis"], 0.0)
        inpatient = claim["jenis_layanan"] == "Rawat Inap"
        total, n = self.provider_ratio[claim["kode_penyedia"]]
        provider_index = (total + math.log(ratio)) / (n + 1 + 20)  # 20 neutral cases: a new provider is not judged on a few bills
        account = claim.get("rekening_penggantian_hash") or ""
        account_members = len(self.account_members[account] | {claim["id_peserta"]}) if account else 0
        phone = self.members.get(claim["id_peserta"], {}).get("telepon_hash", "")
        phone_members = len(self.phone_members.get(phone, set())) if phone else 0
        doctor_day = self.doctor_day[(claim["kode_dokter"], claim["tanggal_masuk"])] + 1
        recent = self.doctor_days[claim["kode_dokter"]]
        since = (_date(claim["tanggal_masuk"]) - timedelta(days=30)).isoformat()
        window = [n for d, n in recent.items() if since <= d < claim["tanggal_masuk"]]
        doctor_rate = (sum(window) + doctor_day) / (len(window) + 1)
        stay_excess = max(0.0, days / usual_days - 1.0) if inpatient and usual_days else 0.0
        stay_total, stays = self.provider_stay[claim["kode_penyedia"]]
        provider_stay = (stay_total + stay_excess) / (stays + (1 if inpatient else 0) + 20)
        same_visit = self.visits[(claim["id_peserta"], claim["tanggal_masuk"], claim["kode_diagnosis"])]
        duplicate = 1.0 if same_visit and claim["kode_penyedia"] not in same_visit else 0.0
        previous = self.last_discharge.get((claim["id_peserta"], claim["kode_diagnosis"]))
        gap = (_date(claim["tanggal_masuk"]) - previous).days if previous and inpatient else None
        readmission = 1.0 if gap is not None and 0 <= gap <= 7 else 0.0
        values = [
            max(0.0, math.log(ratio)),  # a bill below the usual one is not a warning sign
            max(0.0, days / usual_days - 1.0) if inpatient and usual_days else 0.0,
            provider_index,
            math.log(max(account_members, 1)),
            math.log(max(phone_members, 1)),
            math.log(doctor_day),
            math.log(doctor_rate),
            provider_stay,
            duplicate,
            readmission,
        ]
        facts = {
            "rasio_biaya": ratio, "biaya_wajar": self.usual(claim), "hari": days, "hari_wajar": usual_days,
            "rasio_penyedia": math.exp(provider_index), "peserta_rekening": account_members, "peserta_telepon": phone_members,
            "klaim_dokter": doctor_day, "klaim_dokter_rata": doctor_rate, "jeda_rawat_ulang": gap,
            "kelebihan_rawat_penyedia": provider_stay,
        }
        return values, facts

    def remember(self, claim: dict) -> None:
        ratio = min(max(max(float(claim["jumlah_tagihan_idr"] or 0), 1.0) / self.usual(claim), 0.1), 20.0)
        bucket = self.provider_ratio[claim["kode_penyedia"]]
        bucket[0] += math.log(ratio)
        bucket[1] += 1
        if claim.get("rekening_penggantian_hash"):
            self.account_members[claim["rekening_penggantian_hash"]].add(claim["id_peserta"])
        self.doctor_day[(claim["kode_dokter"], claim["tanggal_masuk"])] += 1
        recent = self.doctor_days[claim["kode_dokter"]]
        recent[claim["tanggal_masuk"]] = recent.get(claim["tanggal_masuk"], 0) + 1
        if len(recent) > 45:  # keep the last days only
            cutoff = (_date(claim["tanggal_masuk"]) - timedelta(days=31)).isoformat()
            for d in [d for d in recent if d < cutoff]:
                del recent[d]
        if claim["jenis_layanan"] == "Rawat Inap":
            usual_days = self.usual_days.get(claim["kode_diagnosis"], 0.0)
            stay = self.provider_stay[claim["kode_penyedia"]]
            stay[0] += max(0.0, int(claim.get("lama_rawat_hari") or 0) / usual_days - 1.0) if usual_days else 0.0
            stay[1] += 1
        self.visits[(claim["id_peserta"], claim["tanggal_masuk"], claim["kode_diagnosis"])].add(claim["kode_penyedia"])
        if claim["jenis_layanan"] == "Rawat Inap":
            self.last_discharge[(claim["id_peserta"], claim["kode_diagnosis"])] = _date(claim["tanggal_keluar"])


def rupiah(value: float) -> str:
    if value >= 1_000_000:
        return f"Rp {value / 1_000_000:,.1f} juta".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"Rp {value:,.0f}".replace(",", ".")


def times(value: float) -> str:
    return f"{value:.1f}".replace(".", ",") + "x"


def reason(feature: str, facts: dict) -> str:
    """The sentence an investigator reads for a feature that pushed the score up."""
    if feature == "biaya_vs_wajar":
        return f"Tagihan {times(facts['rasio_biaya'])} biaya wajar untuk diagnosis dan layanan ini (wajar {rupiah(facts['biaya_wajar'])})"
    if feature == "lama_rawat_vs_wajar":
        return f"Dirawat {facts['hari']} hari, biasanya {facts['hari_wajar']:.0f} hari untuk diagnosis ini"
    if feature == "indeks_biaya_penyedia":
        return f"Penyedia ini rata-rata menagih {times(facts['rasio_penyedia'])} penyedia sejenis"
    if feature == "peserta_per_rekening":
        return f"Rekening penggantian dipakai {facts['peserta_rekening']} peserta berbeda"
    if feature == "peserta_per_telepon":
        return f"Nomor telepon peserta dipakai {facts['peserta_telepon']} peserta"
    if feature == "klaim_dokter_hari_itu":
        return f"Dokter mencatat {facts['klaim_dokter']} klaim dari peserta kita pada hari itu"
    if feature == "klaim_dokter_per_hari":
        return f"Dokter rata-rata mencatat {facts['klaim_dokter_rata']:.0f} klaim per hari praktik dalam 30 hari terakhir"
    if feature == "indeks_lama_rawat_penyedia":
        return f"Pasien rawat inap di penyedia ini rata-rata dirawat {facts['kelebihan_rawat_penyedia']:.0%} lebih lama dari biasanya"
    if feature == "klaim_ganda":
        return "Kunjungan yang sama sudah diklaim di penyedia lain"
    if feature == "rawat_ulang_7_hari":
        return f"Rawat inap ulang {facts['jeda_rawat_ulang']} hari setelah pulang, untuk diagnosis yang sama"
    return feature

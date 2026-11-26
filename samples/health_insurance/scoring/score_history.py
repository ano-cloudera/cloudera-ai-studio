#!/usr/bin/env python3
"""Score every historical claim with the example model and write the alerts and the investigators' findings.

Usage: python samples/health_insurance/scoring/score_history.py      (standard library only; needs data/ and scoring/model.json)

Writes data/alert.csv (one row per claim with a score at or above the alert threshold, raised when the claim was filed) and
data/hasil_investigasi.csv (what investigators concluded, appended over time: "Sedang diperiksa", then "Terbukti fraud" or "Bukan
fraud"). The findings are simulated from the planted patterns with realistic mistakes: about 7% of planted claims are cleared and about
8% of the others are confirmed. Alerts raised in the last three weeks are mostly still open. Deterministic.
"""
from __future__ import annotations

import csv
import random
import sys
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from model import DATA, Model, arrival_order, new_context, read  # noqa: E402

END = date(2026, 11, 25)


def main() -> int:
    model = Model.load()
    context = new_context(model.spec)
    truth = {r["id_klaim"]: r["pola"] for r in read("ground_truth.csv")}
    rnd = random.Random(11)
    alerts, findings = [], []
    for claim in arrival_order(read("klaim.csv")):
        values, facts = context.features(claim)
        context.remember(claim)
        result = model.score(values, facts)
        if result["skor_fraud"] < model.alert_at:
            continue
        raised = datetime.combine(date.fromisoformat(claim["tanggal_pengajuan"]), datetime.min.time()) + timedelta(minutes=rnd.randrange(7 * 60, 22 * 60))
        reasons = result["alasan"] + ["", "", ""]
        alert_id = f"ALR-{len(alerts) + 1:07d}"
        alerts.append({
            "id_alert": alert_id, "id_klaim": claim["id_klaim"], "waktu_alert": raised.strftime("%Y-%m-%d %H:%M:%S.000"),
            "skor_fraud": result["skor_fraud"], "tingkat_risiko": result["tingkat_risiko"], "alasan_1": reasons[0], "alasan_2": reasons[1],
            "alasan_3": reasons[2], "versi_model": result["versi_model"],
        })
        age = (END - raised.date()).days
        if age < 2 or rnd.random() > (0.9 if age > 21 else 0.5):
            continue
        opened = raised + timedelta(days=rnd.randint(1, 2), hours=rnd.randint(0, 8))
        findings.append({"id_alert": alert_id, "waktu_hasil": opened.strftime("%Y-%m-%d %H:%M:%S.000"), "status_investigasi": "Sedang diperiksa",
                         "catatan": "Berkas klaim dan riwayat peserta sedang ditinjau"})
        closed = raised + timedelta(days=rnd.randint(7, 40), hours=rnd.randint(0, 8))
        if closed.date() > END:
            continue
        planted = claim["id_klaim"] in truth
        fraud = rnd.random() < 0.93 if planted else rnd.random() < 0.08
        findings.append({
            "id_alert": alert_id, "waktu_hasil": closed.strftime("%Y-%m-%d %H:%M:%S.000"),
            "status_investigasi": "Terbukti fraud" if fraud else "Bukan fraud",
            "catatan": f"Indikasi terbukti: {reasons[0].lower()}" if fraud else "Tidak ditemukan penyimpangan setelah verifikasi dokumen dan konfirmasi penyedia",
        })

    for name, rows in (("alert.csv", alerts), ("hasil_investigasi.csv", findings)):
        with (DATA / name).open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)

    latest = {}
    for f in findings:
        latest[f["id_alert"]] = f["status_investigasi"]
    planted_alerts = sum(1 for a in alerts if a["id_klaim"] in truth)
    print(f"alerts {len(alerts):,} ({planted_alerts / len(alerts):.1%} on planted claims; {Counter(a['tingkat_risiko'] for a in alerts)})")
    print(f"planted claims alerted: {planted_alerts:,} of {len(truth):,}")
    print("latest finding per alert:", dict(Counter(latest.values())), f"open (never looked at): {len(alerts) - len(latest):,}")
    print("example reasons:", alerts[-1]["alasan_1"], "|", alerts[-1]["alasan_2"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

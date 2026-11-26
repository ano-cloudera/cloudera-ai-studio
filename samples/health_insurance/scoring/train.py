#!/usr/bin/env python3
"""Train the example fraud model on the synthetic claims and write scoring/model.json.

Usage (needs scikit-learn, here only; the scoring itself does not): python samples/health_insurance/scoring/train.py

The usual bill (per diagnosis, service and provider class) and the usual inpatient days (per diagnosis) are medians over all claims,
as an insurer would compute them without knowing which claims are fraud. Features are computed in arrival order (features.py). The
labels are the planted patterns (data/ground_truth.csv). A random 30% of the claims is held out, and the report gives, on that part,
how many alerts would be raised and how many planted claims of each pattern they catch. Deterministic.
"""
from __future__ import annotations

import json
import random
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from features import FEATURES  # noqa: E402
from model import MODEL_FILE, Model, arrival_order, new_context, read  # noqa: E402

VERSION = "contoh-logreg-1"


def usual_tables(claims: list[dict], providers: dict[str, str]) -> tuple[dict[str, float], dict[str, float]]:
    bills: dict[str, list[int]] = defaultdict(list)
    days: dict[str, list[int]] = defaultdict(list)
    for c in claims:
        bill = int(c["jumlah_tagihan_idr"])
        bills[f"{c['kode_diagnosis']}|{c['jenis_layanan']}|{providers[c['kode_penyedia']]}"].append(bill)
        bills[f"{c['kode_diagnosis']}|{c['jenis_layanan']}|*"].append(bill)
        if c["jenis_layanan"] == "Rawat Inap":
            days[c["kode_diagnosis"]].append(int(c["lama_rawat_hari"]))
    for c in claims:
        bills[f"{c['kode_diagnosis']}|*|*"].append(int(c["jumlah_tagihan_idr"]))
        bills["*|*|*"].append(int(c["jumlah_tagihan_idr"]))
    return ({k: float(statistics.median(v)) for k, v in bills.items() if len(v) >= 20 or k.endswith("|*|*")},
            {k: float(statistics.median(v)) for k, v in days.items()})


def main() -> int:
    from sklearn.linear_model import LogisticRegression

    claims = read("klaim.csv")
    truth = {r["id_klaim"]: r["pola"] for r in read("ground_truth.csv")}
    klass = {p["kode_penyedia"]: p["kelas"] for p in read("penyedia.csv")}
    usual_cost, usual_days = usual_tables(claims, klass)
    spec = {"version": VERSION, "features": FEATURES, "usual_cost": usual_cost, "usual_days": usual_days}

    context = new_context(spec)
    rows, labels, ids = [], [], []
    for claim in arrival_order(claims):
        values, _ = context.features(claim)
        context.remember(claim)
        rows.append(values)
        labels.append(1 if claim["id_klaim"] in truth else 0)
        ids.append(claim["id_klaim"])

    rnd = random.Random(7)
    test = {i for i in range(len(rows)) if rnd.random() < 0.3}
    train_idx = [i for i in range(len(rows)) if i not in test]
    columns = list(zip(*[rows[i] for i in train_idx]))
    mean = [statistics.fmean(col) for col in columns]
    std = [statistics.pstdev(col) or 1.0 for col in columns]

    def scale(v):
        return [(x - m) / s for x, m, s in zip(v, mean, std)]

    # Every pattern weighs the same in training, whatever its size: a rare pattern (a few hundred long stays) is not drowned by a
    # frequent one (thousands of visits of one doctor). Ordinary claims keep weight 1.
    sizes = Counter(truth[ids[i]] for i in train_idx if labels[i])
    share = sum(sizes.values()) / len(sizes)
    weights = [min(20.0, max(0.5, share / sizes[truth[ids[i]]])) if labels[i] else 1.0 for i in train_idx]
    fit = LogisticRegression(max_iter=5000, C=1.0)
    fit.fit([scale(rows[i]) for i in train_idx], [labels[i] for i in train_idx], sample_weight=weights)
    spec.update(mean=mean, std=std, coef=[float(c) for c in fit.coef_[0]], intercept=float(fit.intercept_[0]))
    spec["thresholds"] = {"alert": 0.5, "high": 0.8}

    model = Model(spec)
    scored = []
    for i in sorted(test):
        z = spec["intercept"] + sum(c * x for c, x in zip(spec["coef"], scale(rows[i])))
        scored.append((1 / (1 + 2.718281828 ** -z), i))
    alerts = [i for p, i in scored if p >= model.alert_at]
    high = [i for p, i in scored if p >= model.high_at]
    planted = [i for i in test if labels[i]]
    caught = Counter(truth[ids[i]] for i in alerts if labels[i])
    total = Counter(truth[ids[i]] for i in planted)
    print(f"held out: {len(test):,} claims, {len(planted):,} planted")
    print(f"alerts (score >= {model.alert_at}): {len(alerts):,} ({len(alerts) / len(test):.2%} of claims); "
          f"{sum(labels[i] for i in alerts) / max(len(alerts), 1):.1%} of them planted; high (>= {model.high_at}): {len(high):,}")
    for pattern in sorted(total):
        print(f"   {pattern:<14} caught {caught[pattern]:>5} of {total[pattern]:>5} ({caught[pattern] / total[pattern]:.0%})")
    print("weights:", ", ".join(f"{f} {c:+.2f}" for f, c in sorted(zip(FEATURES, spec["coef"]), key=lambda t: -abs(t[1]))))

    MODEL_FILE.write_text(json.dumps(spec, indent=1, sort_keys=True), encoding="utf-8")
    print(f"wrote {MODEL_FILE.relative_to(HERE.parents[2])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

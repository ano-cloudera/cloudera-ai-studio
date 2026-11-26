"""The example fraud model as plain numbers (model.json): a logistic regression over the features in features.py. Scoring needs only the
standard library. The reasons are the features that pushed this claim's score up the most, written as sentences with its own figures.

This is an example model trained on synthetic data with planted patterns. It shows how scores and reasons flow into the analysis; it
says nothing about how well any model would detect fraud in real claims.
"""
from __future__ import annotations

import csv
import json
import math
from pathlib import Path

from features import FEATURES, Context, reason

HERE = Path(__file__).resolve().parent
DATA = HERE.parent / "data"
MODEL_FILE = HERE / "model.json"


class Model:
    def __init__(self, spec: dict) -> None:
        if spec["features"] != FEATURES:
            raise ValueError("model.json was trained on other features; run scoring/train.py again")
        self.spec = spec
        self.version = spec["version"]
        self.alert_at = spec["thresholds"]["alert"]
        self.high_at = spec["thresholds"]["high"]

    @classmethod
    def load(cls, path: Path = MODEL_FILE) -> "Model":
        return cls(json.loads(path.read_text(encoding="utf-8")))

    def score(self, values: list[float], facts: dict) -> dict:
        s = self.spec
        scaled = [(v - m) / sd for v, m, sd in zip(values, s["mean"], s["std"])]
        contributions = [c * x for c, x in zip(s["coef"], scaled)]
        z = s["intercept"] + sum(contributions)
        probability = 1.0 / (1.0 + math.exp(-max(-35.0, min(35.0, z))))
        ranked = sorted(((c, f) for c, f in zip(contributions, FEATURES) if c > 0.25), reverse=True)[:3]
        score = round(probability, 4)
        level = "Tinggi" if score >= self.high_at else "Sedang" if score >= self.alert_at else "Rendah"
        return {"skor_fraud": score, "tingkat_risiko": level, "alasan": [reason(f, facts) for _, f in ranked],
                "versi_model": self.version}


def read(name: str) -> list[dict]:
    with (DATA / name).open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def new_context(spec: dict) -> Context:
    members = {m["id_peserta"]: {"telepon_hash": m["telepon_hash"]} for m in read("peserta.csv")}
    providers = {p["kode_penyedia"]: {"kelas": p["kelas"], "status_rekanan": p["status_rekanan"]} for p in read("penyedia.csv")}
    return Context(spec["usual_cost"], spec["usual_days"], members, providers)


def arrival_order(claims: list[dict]) -> list[dict]:
    """Claims in the order they reach the insurer: by the date they are filed."""
    return sorted(claims, key=lambda c: (c["tanggal_pengajuan"], c["id_klaim"]))

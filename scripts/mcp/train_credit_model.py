#!/usr/bin/env python3
"""Train the demo approval-likelihood model and save it as JSON (no ML runtime needed to serve it).

    python scripts/mcp/train_credit_model.py

Needs scikit-learn (training only). The MCP server reads `credit_risk_model.json` and scores with plain Python.
Data is the synthetic demo set in demo/data/credit_applications.csv; nothing here is a real credit model.
"""
from __future__ import annotations

import csv
import json
import math
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "demo" / "data" / "credit_applications.csv"
OUT = Path(__file__).with_name("credit_risk_model.json")

SCORE_THRESHOLD, DTI_THRESHOLD = 650.0, 0.45
CATEGORICAL = ("application_channel", "region_name", "customer_segment", "product_category")


def margins(score: float, dti: float) -> tuple[float, float]:
    return (score - SCORE_THRESHOLD) / 50.0, (DTI_THRESHOLD - dti) / 0.10


def main() -> int:
    try:
        import numpy as np
        from sklearn.linear_model import LogisticRegression
        from sklearn.metrics import accuracy_score, brier_score_loss, roc_auc_score
        from sklearn.model_selection import train_test_split
    except ImportError:
        print("scikit-learn is required to train: pip install scikit-learn", file=sys.stderr)
        return 1

    rows = list(csv.DictReader(DATA.open(encoding="utf-8")))
    categories = {col: sorted({r[col] for r in rows}) for col in CATEGORICAL}
    log_amounts = [math.log(float(r["requested_amount"])) for r in rows]
    mean = sum(log_amounts) / len(log_amounts)
    std = (sum((v - mean) ** 2 for v in log_amounts) / len(log_amounts)) ** 0.5

    names = ["min_margin", "score_margin", "dti_margin", "log_amount"] + [
        f"{col}={value}" for col in CATEGORICAL for value in categories[col]
    ]

    def vector(r: dict) -> list[float]:
        s, d = margins(float(r["credit_score"]), float(r["dti_ratio"]))
        base = [min(s, d), s, d, (math.log(float(r["requested_amount"])) - mean) / std]
        return base + [1.0 if r[col] == value else 0.0 for col in CATEGORICAL for value in categories[col]]

    X = np.array([vector(r) for r in rows])
    y = np.array([1 if r["decision_status"] == "Approved" else 0 for r in rows])
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)

    model = LogisticRegression(C=1.0, max_iter=5000)
    model.fit(X_train, y_train)
    proba = model.predict_proba(X_test)[:, 1]
    metrics = {
        "holdout_rows": int(len(y_test)),
        "roc_auc": round(float(roc_auc_score(y_test, proba)), 4),
        "accuracy": round(float(accuracy_score(y_test, proba >= 0.5)), 4),
        "brier": round(float(brier_score_loss(y_test, proba)), 4),
    }
    payload = {
        "name": "credit-approval-likelihood",
        "version": "1.0",
        "algorithm": "logistic regression (L2, C=1.0)",
        "trained_on": f"synthetic credit_applications.csv ({len(rows)} rows)",
        "trained_at": date.today().isoformat(),
        "thresholds": {"credit_score": SCORE_THRESHOLD, "dti_ratio": DTI_THRESHOLD},
        "log_amount": {"mean": mean, "std": std},
        "categories": categories,
        "feature_names": names,
        "intercept": float(model.intercept_[0]),
        "coefficients": {n: round(float(c), 6) for n, c in zip(names, model.coef_[0])},
        "metrics": metrics,
    }
    OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}  metrics={metrics}")
    for name in ("min_margin", "score_margin", "dti_margin", "log_amount"):
        print(f"  {name:14s} {payload['coefficients'][name]:+.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Score an application with the demo approval-likelihood model (pure Python, no ML runtime).

The coefficients come from `train_credit_model.py` and live in `credit_risk_model.json`. The result is an
advisory risk indicator on synthetic data: it never approves or rejects, and a human decides.
"""
from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path
from typing import Any

MODEL_PATH = Path(__file__).with_name("credit_risk_model.json")

GUARDRAIL = (
    "Advisory risk indicator on synthetic demo data. It is not a credit decision: no application is approved "
    "or rejected here, and a human reviewer must decide."
)


@lru_cache(maxsize=1)
def load_model(path: str | None = None) -> dict[str, Any]:
    return json.loads(Path(path or MODEL_PATH).read_text(encoding="utf-8"))


def _sigmoid(value: float) -> float:
    if value >= 0:
        return 1.0 / (1.0 + math.exp(-value))
    exp = math.exp(value)
    return exp / (1.0 + exp)


def _band(probability: float) -> str:
    if probability >= 0.75:
        return "High"
    if probability >= 0.40:
        return "Moderate"
    return "Low"


def _normalize_dti(value: float) -> float:
    """Accept 0.40 or 40 (percent) and return a fraction."""
    if 1.0 < value <= 100.0:
        return value / 100.0
    return value


def _match_category(model: dict[str, Any], column: str, value: str | None) -> str | None:
    if not value:
        return None
    wanted = value.strip().casefold()
    for known in model["categories"].get(column, []):
        if known.casefold() == wanted:
            return known
    return None


def assess(
    credit_score: float,
    dti_ratio: float,
    requested_amount: float | None = None,
    application_channel: str | None = None,
    region_name: str | None = None,
    customer_segment: str | None = None,
    product_category: str | None = None,
    *,
    model: dict[str, Any] | None = None,
) -> dict[str, Any]:
    model = model or load_model()
    score = float(credit_score)
    if not 300 <= score <= 850:
        raise ValueError("credit_score must be between 300 and 850")
    dti = _normalize_dti(float(dti_ratio))
    if not 0 < dti <= 1.5:
        raise ValueError("dti_ratio must be a fraction such as 0.40 (or a percentage such as 40)")
    if requested_amount is not None and float(requested_amount) <= 0:
        raise ValueError("requested_amount must be positive")

    score_threshold = float(model["thresholds"]["credit_score"])
    dti_threshold = float(model["thresholds"]["dti_ratio"])
    score_margin = (score - score_threshold) / 50.0
    dti_margin = (dti_threshold - dti) / 0.10

    values: dict[str, float] = {
        "min_margin": min(score_margin, dti_margin),
        "score_margin": score_margin,
        "dti_margin": dti_margin,
        "log_amount": 0.0,
    }
    if requested_amount is not None:
        stats = model["log_amount"]
        values["log_amount"] = (math.log(float(requested_amount)) - stats["mean"]) / stats["std"]

    given = {
        "application_channel": _match_category(model, "application_channel", application_channel),
        "region_name": _match_category(model, "region_name", region_name),
        "customer_segment": _match_category(model, "customer_segment", customer_segment),
        "product_category": _match_category(model, "product_category", product_category),
    }
    for column, value in given.items():
        if value:
            values[f"{column}={value}"] = 1.0

    coefficients = model["coefficients"]
    logit = float(model["intercept"]) + sum(float(coefficients.get(name, 0.0)) * x for name, x in values.items())
    # Never claim certainty: the model is trained on synthetic data and is advisory only.
    probability = min(0.999, max(0.001, _sigmoid(logit)))

    score_ok, dti_ok = score >= score_threshold, dti <= dti_threshold
    meets = score_ok and dti_ok
    binding = "credit_score" if score_margin <= dti_margin else "dti_ratio"

    drivers: list[str] = []
    gap_score = score - score_threshold
    drivers.append(
        f"Credit score {score:.0f} is {abs(gap_score):.0f} points {'above' if gap_score >= 0 else 'below'} "
        f"the {score_threshold:.0f} policy threshold."
    )
    gap_dti = dti_threshold - dti
    drivers.append(
        f"DTI {dti:.2f} is {abs(gap_dti):.2f} {'under' if gap_dti >= 0 else 'over'} "
        f"the {dti_threshold:.2f} limit."
    )
    if not meets:
        drivers.append(
            f"The {'credit score' if binding == 'credit_score' else 'DTI'} is the binding constraint; "
            "an approval outside the standard criteria must be recorded as a policy exception."
        )
    else:
        drivers.append("Both standard criteria are met; the weaker margin sets the likelihood.")
    context = [
        name
        for name, x in values.items()
        if "=" in name and abs(float(coefficients.get(name, 0.0)) * x) >= 0.25
    ]
    drivers.append(
        "Channel, region, segment and product have little influence in this model."
        if not context
        else "Notable context effects: " + ", ".join(sorted(context)) + "."
    )

    metrics = model.get("metrics", {})
    return {
        "approval_likelihood": round(probability, 3),
        "likelihood_band": _band(probability),
        "policy_check": {
            "credit_score": {"value": score, "threshold": score_threshold, "ok": score_ok},
            "dti_ratio": {"value": round(dti, 3), "threshold": dti_threshold, "ok": dti_ok},
            "meets_standard_criteria": meets,
            "policy_exception_required_for_approval": not meets,
        },
        "inputs_used": {
            "credit_score": score,
            "dti_ratio": round(dti, 3),
            "requested_amount": requested_amount,
            **{k: v for k, v in given.items() if v},
        },
        "drivers": drivers,
        "model": {
            "name": model["name"],
            "version": model["version"],
            "algorithm": model["algorithm"],
            "trained_on": model["trained_on"],
            "holdout_roc_auc": metrics.get("roc_auc"),
            "holdout_accuracy": metrics.get("accuracy"),
        },
        "guardrail": GUARDRAIL,
    }

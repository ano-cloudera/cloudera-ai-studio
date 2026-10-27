#!/usr/bin/env python3
"""Fix common Banking Analytics draft issues before publish (glossary + dimension descriptions)."""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request

BASE = os.environ.get("GOLDEN_PATH_API_BASE", "http://127.0.0.1:8001")

MODEL_KEYS = (
    os.environ.get("BANKING_SEMANTIC_MODEL_KEY", "banking_analytics"),
    "retail_banking_analytics",
    "banking_analytics",
)

# Old auto-suggest / OSSIE metric keys → preferred replacements (first match wins).
METRIC_KEY_REMAP: dict[str, tuple[str, ...]] = {
    "transactions_amount_total": ("total_amount", "total_transaction_amount", "transactions_amount_total"),
    "transactions_customer_id_total": ("transaction_count", "transactions_customer_id_total"),
    "customers_customer_id_total": ("active_customers", "customers_customer_id_total"),
}

DIM_DESCRIPTIONS_BY_COLUMN: dict[str, str] = {
    "segment": "Banking customer segment (e.g. Priority, Standard).",
    "city": "Customer city for geographic breakdowns.",
    "risk_tier": "Synthetic risk tier classification.",
    "customer_status": "Customer lifecycle status (Active/Inactive).",
    "transaction_type": "Transaction type label.",
    "channel": "Origination channel (Branch, Mobile, etc.).",
    "merchant_category": "Merchant category for the transaction.",
    "status": "Transaction attempt outcome (Success or Failed).",
    "transaction_date": "Calendar date of the transaction.",
    "transaction_month": "Month bucket derived from transaction_date.",
    "amount": "Transaction monetary amount.",
    "customer_name": "Customer display name.",
    "join_date": "Date the customer joined.",
    "customer_id": "Surrogate customer identifier.",
    "transaction_id": "Surrogate transaction identifier.",
}


def req(method: str, path: str, body: dict | None = None) -> tuple[int, dict | str]:
    payload = None if body is None else json.dumps(body).encode()
    headers = {"Content-Type": "application/json"} if body is not None else {}
    request = urllib.request.Request(BASE + path, data=payload, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=120) as resp:
            raw = resp.read().decode()
            try:
                return resp.status, json.loads(raw)
            except json.JSONDecodeError:
                return resp.status, raw
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except json.JSONDecodeError:
            return e.code, raw


def _find_model() -> dict:
    st, body = req("GET", "/api/v1/semantic/models")
    if st != 200:
        raise RuntimeError(f"list models failed: {st} {body}")
    models = body.get("models") or []
    for key in MODEL_KEYS:
        row = next((m for m in models if m.get("key") == key), None)
        if row:
            return row
    row = next((m for m in models if "banking" in (m.get("name") or "").lower()), None)
    if row:
        return row
    raise RuntimeError("No Banking semantic model found")


def _draft_version_id(model_id: str, *, clone_if_needed: bool) -> str:
    st, body = req("GET", f"/api/v1/semantic/models/{model_id}/versions")
    if st != 200:
        raise RuntimeError(f"list versions failed: {st} {body}")
    versions = body.get("versions") or []
    draft = next((v for v in versions if v.get("status") == "DRAFT"), None)
    if draft:
        return draft["id"]
    if not clone_if_needed:
        active = next((v for v in versions if v.get("status") == "ACTIVE"), None)
        if active:
            return active["id"]
        raise RuntimeError("No DRAFT version — click Edit in Semantic Layer or pass --clone-draft")
    active = next((v for v in versions if v.get("status") == "ACTIVE"), None)
    if active:
        st2, cloned = req("POST", f"/api/v1/semantic/versions/{active['id']}/clone")
        if st2 != 200:
            raise RuntimeError(f"clone failed: {st2} {cloned}")
        return cloned["version"]["id"]
    if versions:
        return versions[0]["id"]
    raise RuntimeError("No semantic version")


def _resolve_metric_keys(metrics: list[dict]) -> dict[str, str]:
    """Map legacy metric key → existing metric key on this version."""
    by_key = {m["key"]: m for m in metrics}
    by_expr = {(m.get("expression") or "").strip().upper(): m["key"] for m in metrics}

    def pick(candidates: tuple[str, ...]) -> str | None:
        for c in candidates:
            if c in by_key:
                return c
        if "SUM(AMOUNT)" in by_expr and "transactions_amount_total" in candidates:
            return by_expr["SUM(AMOUNT)"]
        return None

    out: dict[str, str] = {}
    for legacy, candidates in METRIC_KEY_REMAP.items():
        resolved = pick(candidates)
        if resolved:
            out[legacy] = resolved
    return out


def _description_for_dimension(dim: dict) -> str | None:
    if (dim.get("description") or "").strip():
        return None
    col = (dim.get("source_column") or "").strip()
    if col and col in DIM_DESCRIPTIONS_BY_COLUMN:
        return DIM_DESCRIPTIONS_BY_COLUMN[col]
    key = dim.get("key") or ""
    tail = key.split("_")[-1] if "_" in key else key
    if tail in DIM_DESCRIPTIONS_BY_COLUMN:
        return DIM_DESCRIPTIONS_BY_COLUMN[tail]
    m = re.search(r"_(segment|city|channel|status|amount|join_date|risk_tier|customer_name|transaction_date)$", key)
    if m and m.group(1) in DIM_DESCRIPTIONS_BY_COLUMN:
        return DIM_DESCRIPTIONS_BY_COLUMN[m.group(1)]
    name = (dim.get("name") or key).replace("_", " ")
    return f"Business attribute: {name}."


def patch_version(version_id: str) -> dict:
    report: dict = {"terms_patched": [], "dimensions_patched": [], "term_metric_remap": {}}

    st, mbody = req("GET", f"/api/v1/semantic/versions/{version_id}/metrics")
    if st != 200:
        raise RuntimeError(f"list metrics failed: {st}")
    metrics = mbody.get("metrics") or []
    metric_keys = {m["key"] for m in metrics}
    remap = _resolve_metric_keys(metrics)
    report["term_metric_remap"] = remap

    st, tbody = req("GET", f"/api/v1/semantic/versions/{version_id}/terms")
    if st != 200:
        raise RuntimeError(f"list terms failed: {st}")
    for term in tbody.get("terms") or []:
        related = list(term.get("related_metric_keys") or [])
        if not related:
            continue
        new_related: list[str] = []
        changed = False
        for mk in related:
            if mk in metric_keys:
                new_related.append(mk)
                continue
            replacement = remap.get(mk)
            if replacement and replacement in metric_keys:
                new_related.append(replacement)
                changed = True
                continue
            # drop unknown refs
            if mk not in metric_keys:
                changed = True
                continue
            new_related.append(mk)
        new_related = list(dict.fromkeys(new_related))
        patch: dict = {}
        if changed:
            patch["related_metric_keys"] = new_related
        if not (term.get("definition") or "").strip():
            patch["definition"] = term.get("term") or term.get("key") or "Glossary term."
        if patch:
            stp, _ = req("PATCH", f"/api/v1/semantic/versions/{version_id}/terms/{term['id']}", patch)
            if stp == 200:
                report["terms_patched"].append({"key": term.get("key"), "patch": patch})

    st, dbody = req("GET", f"/api/v1/semantic/versions/{version_id}/dimensions")
    if st != 200:
        raise RuntimeError(f"list dimensions failed: {st}")
    for dim in dbody.get("dimensions") or []:
        desc = _description_for_dimension(dim)
        if not desc:
            continue
        stp, _ = req(
            "PATCH",
            f"/api/v1/semantic/versions/{version_id}/dimensions/{dim['id']}",
            {"description": desc},
        )
        if stp == 200:
            report["dimensions_patched"].append(dim.get("key"))

    st, val = req("POST", f"/api/v1/semantic/versions/{version_id}/validate", {"mode": "full"})
    if st == 200 and isinstance(val, dict):
        summary = val.get("summary") or {}
        report["validation"] = {
            "valid": val.get("valid"),
            "error_count": summary.get("error_count"),
            "warning_count": summary.get("warning_count"),
        }
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clone-draft", action="store_true", help="Clone ACTIVE to DRAFT if no draft exists")
    parser.add_argument("--dry-run", action="store_true", help="Only print model/version ids")
    args = parser.parse_args()

    health, _ = req("GET", "/health")
    if health != 200:
        print("Backend not healthy at", BASE, file=sys.stderr)
        return 1

    model = _find_model()
    version_id = _draft_version_id(model["id"], clone_if_needed=args.clone_draft)
    print(f"Model: {model.get('name')} ({model.get('key')})")
    print(f"Version: {version_id}")

    if args.dry_run:
        return 0

    report = patch_version(version_id)
    print(json.dumps(report, indent=2))
    val = report.get("validation") or {}
    if val.get("valid"):
        print("\nDraft validation OK — try Publish in Semantic Layer.")
        return 0
    print("\nSome issues may remain — check Preview/Publish in UI.", file=sys.stderr)
    return 0 if val.get("error_count", 1) == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

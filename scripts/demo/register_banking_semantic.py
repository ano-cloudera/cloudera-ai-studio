#!/usr/bin/env python3
"""Register Golden Banking semantic model (Retail Banking Analytics) via API."""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "demo"))

from golden_banking_semantic_constants import (  # noqa: E402
    BANKING_SCHEMA,
    CUSTOMERS_TABLE,
    ENTITY_CUSTOMERS_KEY,
    ENTITY_TRANSACTIONS_KEY,
    EXTRA_DIMENSIONS,
    GLOSSARY_SPECS,
    METRIC_SPECS,
    MODEL_DESCRIPTION,
    MODEL_KEY,
    MODEL_NAME,
    REGISTRATION_EVIDENCE,
    RELATIONSHIP_SPEC,
    TRANSACTIONS_TABLE,
)

BASE = os.environ.get("GOLDEN_PATH_API_BASE", "http://127.0.0.1:8001")
CONNECTOR_KEY = os.environ.get("BANKING_CONNECTOR_KEY", "golden_banking_pg")

CUSTOMER_DIM_COLUMNS = [
    "customer_name",
    "segment",
    "city",
    "join_date",
    "customer_status",
    "risk_tier",
]
TRANSACTION_DIM_COLUMNS = [
    "transaction_date",
    "transaction_type",
    "channel",
    "merchant_category",
    "amount",
    "status",
]


def req(method: str, path: str, body: dict | None = None) -> tuple[int, dict | str]:
    payload = None if body is None else json.dumps(body).encode()
    headers = {"Content-Type": "application/json"} if body is not None else {}
    request = urllib.request.Request(BASE + path, data=payload, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=180) as resp:
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


def _connector_id() -> str:
    st, body = req("GET", "/api/v1/connectors")
    if st != 200:
        raise RuntimeError(f"list connectors failed: {st} {body}")
    row = next((c for c in body["connectors"] if c.get("key") == CONNECTOR_KEY), None)
    if not row:
        raise RuntimeError(f"connector key {CONNECTOR_KEY} not found — run register_banking_connector.py")
    return row["id"]


def _find_model() -> dict | None:
    st, body = req("GET", "/api/v1/semantic/models")
    if st != 200:
        raise RuntimeError(f"list models failed: {st}")
    return next((m for m in body.get("models", []) if m.get("key") == MODEL_KEY), None)


def _draft_version_id(model_id: str) -> str:
    st, body = req("GET", f"/api/v1/semantic/models/{model_id}/versions")
    if st != 200:
        raise RuntimeError(f"list versions failed: {st}")
    versions = body.get("versions") or []
    draft = next((v for v in versions if v.get("status") == "DRAFT"), None)
    if draft:
        return draft["id"]
    active = next((v for v in versions if v.get("status") == "ACTIVE"), None)
    if active:
        st2, cloned = req("POST", f"/api/v1/semantic/versions/{active['id']}/clone")
        if st2 != 200:
            raise RuntimeError(f"clone active version failed: {st2} {cloned}")
        return cloned["version"]["id"]
    if versions:
        return versions[0]["id"]
    raise RuntimeError("no semantic version for model")


def _entity_keys(version_id: str) -> set[str]:
    st, body = req("GET", f"/api/v1/semantic/versions/{version_id}/entities")
    if st != 200:
        raise RuntimeError(f"list entities failed: {st}")
    return {e["key"] for e in body.get("entities") or []}


def _import_entity(version_id: str, connector_id: str, *, table: str, key: str, name: str, dims: list[str]) -> None:
    st, body = req(
        "POST",
        f"/api/v1/semantic/versions/{version_id}/entities/import",
        {
            "connector_id": connector_id,
            "schema": BANKING_SCHEMA,
            "table": table,
            "key": key,
            "name": name,
            "dimension_columns": dims,
        },
    )
    if st not in (200, 409):
        raise RuntimeError(f"import {key} failed: {st} {body}")


def _repair_entity_connectors(version_id: str, connector_id: str) -> None:
    st, body = req("GET", f"/api/v1/semantic/versions/{version_id}/entities")
    if st != 200:
        return
    for ent in body.get("entities") or []:
        if ent.get("connection_id"):
            continue
        if ent.get("source_type") not in ("postgres", "trino", "impala"):
            continue
        req(
            "PATCH",
            f"/api/v1/semantic/versions/{version_id}/entities/{ent['id']}",
            {"connection_id": connector_id},
        )


def _ensure_dimension(version_id: str, spec: dict) -> None:
    st, existing = req("GET", f"/api/v1/semantic/versions/{version_id}/dimensions")
    if st != 200:
        raise RuntimeError(f"list dimensions failed: {st}")
    if any(d.get("key") == spec["key"] for d in existing.get("dimensions") or []):
        return
    st2, body = req("POST", f"/api/v1/semantic/versions/{version_id}/dimensions", spec)
    if st2 != 200:
        raise RuntimeError(f"create dimension {spec['key']} failed: {st2} {body}")


def _ensure_metric(version_id: str, spec: dict) -> None:
    st, existing = req("GET", f"/api/v1/semantic/versions/{version_id}/metrics")
    if st != 200:
        raise RuntimeError(f"list metrics failed: {st}")
    row = next((m for m in existing.get("metrics") or [] if m.get("key") == spec["key"]), None)
    if row:
        patch = {
            k: spec[k]
            for k in ("expression", "name", "business_definition", "aggregation", "format", "synonyms")
            if k in spec and row.get(k) != spec[k]
        }
        if "synonyms" in spec:
            merged = list(row.get("synonyms") or [])
            changed = False
            for syn in spec["synonyms"]:
                if syn not in merged:
                    merged.append(syn)
                    changed = True
            if changed and merged != list(row.get("synonyms") or []):
                patch["synonyms"] = merged
        if not patch:
            return
        st2, body = req("PATCH", f"/api/v1/semantic/versions/{version_id}/metrics/{row['id']}", patch)
        if st2 != 200:
            raise RuntimeError(f"patch metric {spec['key']} failed: {st2} {body}")
        return
    st2, body = req("POST", f"/api/v1/semantic/versions/{version_id}/metrics", spec)
    if st2 != 200:
        raise RuntimeError(f"create metric {spec['key']} failed: {st2} {body}")


def _ensure_relationship(version_id: str) -> None:
    st, existing = req("GET", f"/api/v1/semantic/versions/{version_id}/relationships")
    if st != 200:
        raise RuntimeError(f"list relationships failed: {st}")
    row = next((r for r in existing.get("relationships") or [] if r.get("key") == RELATIONSHIP_SPEC["key"]), None)
    if row:
        if row.get("join_expression") != RELATIONSHIP_SPEC["join_expression"]:
            req(
                "PATCH",
                f"/api/v1/semantic/versions/{version_id}/relationships/{row['id']}",
                {"join_expression": RELATIONSHIP_SPEC["join_expression"]},
            )
        return
    st2, body = req("POST", f"/api/v1/semantic/versions/{version_id}/relationships", RELATIONSHIP_SPEC)
    if st2 != 200:
        raise RuntimeError(f"create relationship failed: {st2} {body}")


def _ensure_glossary(version_id: str) -> None:
    st, existing = req("GET", f"/api/v1/semantic/versions/{version_id}/terms")
    if st != 200:
        raise RuntimeError(f"list terms failed: {st}")
    rows = {t.get("key"): t for t in existing.get("terms") or []}
    for spec in GLOSSARY_SPECS:
        row = rows.get(spec["key"])
        if row:
            patch = {
                k: spec[k]
                for k in ("term", "definition", "related_metric_keys", "related_dimension_keys", "synonyms")
                if k in spec and row.get(k) != spec.get(k)
            }
            if "synonyms" in spec:
                merged = list(row.get("synonyms") or [])
                changed = False
                for syn in spec["synonyms"]:
                    if syn not in merged:
                        merged.append(syn)
                        changed = True
                if changed and merged != list(row.get("synonyms") or []):
                    patch["synonyms"] = merged
            if patch:
                req("PATCH", f"/api/v1/semantic/versions/{version_id}/terms/{row['id']}", patch)
            continue
        st2, body = req("POST", f"/api/v1/semantic/versions/{version_id}/terms", spec)
        if st2 != 200:
            raise RuntimeError(f"create term {spec['key']} failed: {st2} {body}")


def _rename_dimensions(version_id: str) -> None:
    """Apply human-friendly labels for imported column dimensions."""
    labels = {
        "segment": "Customer Segment",
        "city": "Customer City",
        "risk_tier": "Risk Tier",
        "customer_status": "Customer Status",
        "transaction_type": "Transaction Type",
        "channel": "Channel",
        "merchant_category": "Merchant Category",
        "status": "Transaction Status",
        "transaction_date": "Transaction Date",
        "transaction_month": "Transaction Month",
        "amount": "Transaction Amount",
        "customer_name": "Customer Name",
        "join_date": "Customer Join Date",
    }
    descriptions = {
        "segment": "Banking customer segment (e.g. Priority, Standard).",
        "city": "Customer city.",
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
    st, body = req("GET", f"/api/v1/semantic/versions/{version_id}/dimensions")
    if st != 200:
        return
    for dim in body.get("dimensions") or []:
        key = dim.get("key")
        patch: dict = {}
        if key in labels and dim.get("name") != labels[key]:
            patch["name"] = labels[key]
        if key in descriptions and not (dim.get("description") or "").strip():
            patch["description"] = descriptions[key]
        if patch:
            req("PATCH", f"/api/v1/semantic/versions/{version_id}/dimensions/{dim['id']}", patch)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-publish", action="store_true")
    parser.add_argument("--force-rebuild", action="store_true", help="Rebuild draft even if entities exist")
    parser.add_argument(
        "--patch-auto-metrics",
        action="store_true",
        help="Also patch auto-suggested banking_demo metric keys on every semantic model (then publish)",
    )
    args = parser.parse_args()

    health, _ = req("GET", "/health")
    if health != 200:
        print("backend not healthy", file=sys.stderr)
        return 1

    connector_id = _connector_id()
    model = _find_model()
    if not model:
        st, created = req(
            "POST",
            "/api/v1/semantic/models",
            {"name": MODEL_NAME, "key": MODEL_KEY, "description": MODEL_DESCRIPTION},
        )
        if st != 200:
            print("create model failed", st, created, file=sys.stderr)
            return 1
        model = created["model"]
    else:
        req(
            "PATCH",
            f"/api/v1/semantic/models/{model['id']}",
            {"name": MODEL_NAME, "description": MODEL_DESCRIPTION},
        )

    model_id = model["id"]
    version_id = _draft_version_id(model_id)
    if args.force_rebuild:
        st, versions = req("GET", f"/api/v1/semantic/models/{model_id}/versions")
        active = next((v for v in (versions.get("versions") or []) if v.get("status") == "ACTIVE"), None)
        if active:
            st_clone, cloned = req("POST", f"/api/v1/semantic/versions/{active['id']}/clone")
            if st_clone == 200:
                version_id = cloned["version"]["id"]
    keys = _entity_keys(version_id)
    if args.force_rebuild or ENTITY_CUSTOMERS_KEY not in keys:
        _import_entity(
            version_id,
            connector_id,
            table=CUSTOMERS_TABLE,
            key=ENTITY_CUSTOMERS_KEY,
            name="Customers",
            dims=CUSTOMER_DIM_COLUMNS,
        )
    if args.force_rebuild or ENTITY_TRANSACTIONS_KEY not in keys:
        _import_entity(
            version_id,
            connector_id,
            table=TRANSACTIONS_TABLE,
            key=ENTITY_TRANSACTIONS_KEY,
            name="Transactions",
            dims=TRANSACTION_DIM_COLUMNS,
        )
    _repair_entity_connectors(version_id, connector_id)

    for spec in EXTRA_DIMENSIONS:
        _ensure_dimension(version_id, spec)
    _rename_dimensions(version_id)

    for spec in METRIC_SPECS:
        _ensure_metric(version_id, spec)
    _ensure_relationship(version_id)
    _ensure_glossary(version_id)

    if args.patch_auto_metrics:
        import subprocess

        patch_argv = [sys.executable, str(ROOT / "scripts/demo/patch_banking_auto_metrics.py")]
        if args.skip_publish:
            patch_argv.append("--skip-publish")
        proc = subprocess.run(patch_argv, cwd=ROOT, capture_output=True, text=True)
        if proc.returncode != 0:
            print(proc.stderr or proc.stdout, file=sys.stderr)
            return 1

    val_st, validation = req(
        "POST",
        f"/api/v1/semantic/versions/{version_id}/validate",
        {"mode": "full", "source_mode": "safe_query"},
    )
    if val_st != 200:
        print("validate failed", val_st, validation, file=sys.stderr)
        return 1

    publish_result: dict | None = None
    if not args.skip_publish:
        pub_st, pub_body = req(
            "POST",
            f"/api/v1/semantic/models/{model_id}/publish-to-ask-data",
            {"version_id": version_id},
        )
        if pub_st not in (200, 422, 502):
            print("publish failed", pub_st, pub_body, file=sys.stderr)
            return 1
        if pub_st != 200:
            print("publish blocked", pub_st, json.dumps(pub_body, indent=2), file=sys.stderr)
            return 1
        publish_result = pub_body if isinstance(pub_body, dict) else {"raw": pub_body}

    rt_st, runtime = req("GET", f"/api/v1/semantic/runtime/status?model_key={MODEL_KEY}")
    evidence = {
        "model_id": model_id,
        "model_key": MODEL_KEY,
        "draft_version_id": version_id,
        "connector_id": connector_id,
        "validation": validation,
        "publish": publish_result,
        "runtime_status": runtime if rt_st == 200 else None,
    }
    REGISTRATION_EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    REGISTRATION_EVIDENCE.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(json.dumps(evidence, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

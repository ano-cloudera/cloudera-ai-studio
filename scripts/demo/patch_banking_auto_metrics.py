#!/usr/bin/env python3
"""Patch auto-suggested banking_demo metrics (labels, COUNT expressions, synonyms) and republish."""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.semantic.banking_demo_catalog import METRIC_ENRICHMENT, coerce_suggested_metric_metadata  # noqa: E402

BASE = os.environ.get("GOLDEN_PATH_API_BASE", "http://127.0.0.1:8001")
EVIDENCE = ROOT / "testing" / "evidence" / "golden-path" / "PHASE3-SEMANTIC" / "patch-auto-metrics.json"


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


def _draft_version_id(model_id: str) -> str | None:
    st, body = req("GET", f"/api/v1/semantic/models/{model_id}/versions")
    if st != 200:
        return None
    versions = body.get("versions") or []
    draft = next((v for v in versions if v.get("status") == "DRAFT"), None)
    if draft:
        return draft["id"]
    active = next((v for v in versions if v.get("status") == "ACTIVE"), None)
    if active:
        st2, cloned = req("POST", f"/api/v1/semantic/versions/{active['id']}/clone")
        if st2 == 200:
            return cloned["version"]["id"]
    return versions[0]["id"] if versions else None


def _patch_version_metrics(version_id: str) -> list[dict]:
    st, body = req("GET", f"/api/v1/semantic/versions/{version_id}/metrics")
    if st != 200:
        raise RuntimeError(f"list metrics failed: {st} {body}")
    patched: list[dict] = []
    for row in body.get("metrics") or []:
        key = str(row.get("key") or "")
        if key not in METRIC_ENRICHMENT:
            continue
        display, expr, definition = coerce_suggested_metric_metadata(
            key=key,
            expression=str(row.get("expression") or ""),
            name=str(row.get("name") or ""),
        )
        enrich = METRIC_ENRICHMENT[key]
        synonyms = list(row.get("synonyms") or [])
        for syn in enrich.get("synonyms") or []:
            if syn not in synonyms:
                synonyms.append(syn)
        patch: dict = {}
        if row.get("name") != display:
            patch["name"] = display
        if row.get("expression") != expr:
            patch["expression"] = expr
        biz = row.get("business_definition") or row.get("description") or ""
        if definition and biz != definition:
            patch["business_definition"] = definition
        if synonyms != list(row.get("synonyms") or []):
            patch["synonyms"] = synonyms
        if not patch:
            continue
        st2, resp = req("PATCH", f"/api/v1/semantic/versions/{version_id}/metrics/{row['id']}", patch)
        if st2 != 200:
            raise RuntimeError(f"patch {key} failed: {st2} {resp}")
        patched.append({"key": key, "patch": patch})
    return patched


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-key", action="append", default=[], help="Limit to model keys (default: all)")
    parser.add_argument("--skip-publish", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    st, body = req("GET", "/api/v1/semantic/models")
    if st != 200:
        print("list models failed", st, body, file=sys.stderr)
        return 1

    keys_filter = set(args.model_key) if args.model_key else None
    report: dict = {"models": []}
    for model in body.get("models") or []:
        model_key = str(model.get("key") or "")
        if keys_filter and model_key not in keys_filter:
            continue
        version_id = _draft_version_id(model["id"])
        if not version_id:
            continue
        if args.dry_run:
            report["models"].append({"model_key": model_key, "version_id": version_id, "dry_run": True})
            continue
        patched = _patch_version_metrics(version_id)
        pub: dict | None = None
        if patched and not args.skip_publish:
            pub_st, pub_body = req(
                "POST",
                f"/api/v1/semantic/models/{model['id']}/publish-to-ask-data",
                {"version_id": version_id},
            )
            pub = {"status": pub_st, "body": pub_body if pub_st == 200 else str(pub_body)[:500]}
        report["models"].append(
            {
                "model_key": model_key,
                "model_id": model["id"],
                "version_id": version_id,
                "patched": patched,
                "publish": pub,
            }
        )

    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

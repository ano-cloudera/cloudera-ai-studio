"""Create, validate and publish a semantic model through the Backend API (stdlib only), from a plain spec.

A sample (samples/<name>/build_semantic_model.py) defines a SPEC and calls `main(SPEC, argv)`. The Backend URL (with its secret path)
is derived the way the deploy Job does it, so the script runs in a Cloudera AI Session; pass --base-url to use another one.
Every run adds a new version of the model (a published version is never edited). Nothing secret is printed.

SPEC keys:
  key, name, description, catalog, schema
  entities    [{"key", "name", "table", "kind" ("table" | "view"), "primary_key", "description"}]
  dimensions  [(key, name, entity key, column, data type, synonyms, description)]
  metrics     [(key, name, entity key, expression, unit, synonyms, business definition)]
  headline    optional list of metric keys an overview starts with, most important first
  terms       [(key, term, definition, related metric keys)]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent


class ApiError(RuntimeError):
    pass


def entity_payload(spec: dict, entity: dict, connector_id: str) -> dict:
    return {
        "key": entity["key"], "name": entity["name"], "description": entity["description"], "source_type": "trino",
        "catalog": spec["catalog"], "db_schema": spec["schema"], "table_name": entity["table"] if entity["kind"] == "table" else None,
        "view_name": entity["table"] if entity["kind"] == "view" else None, "primary_key": entity["primary_key"], "connection_id": connector_id,
    }


def dimension_payload(row: tuple) -> dict:
    key, name, entity, column, data_type, synonyms, description = row
    return {"key": key, "name": name, "source_entity_key": entity, "source_column": column, "data_type": data_type, "synonyms": synonyms, "description": description}


def metric_payload(row: tuple, dimension_keys: dict[str, list[str]], headline: list[str] | None = None) -> dict:
    key, name, entity, expression, unit, synonyms, definition = row
    payload = {
        "key": key, "name": name, "expression": expression, "source_entity_key": entity, "description": definition,
        "business_definition": definition, "unit": unit, "synonyms": synonyms, "allowed_dimension_keys": dimension_keys[entity],
    }
    if key in (headline or []):
        # The figures an overview starts with, most important first.
        payload["metadata"] = {"reference_extension": {"headline": (headline or []).index(key) + 1}}
    return payload


def term_payload(row: tuple) -> dict:
    key, term, definition, metric_keys = row
    return {"key": key, "term": term, "definition": definition, "synonyms": [], "related_metric_keys": metric_keys}


def plan(spec: dict, connector_id: str) -> dict[str, list[dict]]:
    keys: dict[str, list[str]] = {e["key"]: [] for e in spec["entities"]}
    for row in spec["dimensions"]:
        keys[row[2]].append(row[0])
    return {
        "entities": [entity_payload(spec, e, connector_id) for e in spec["entities"]],
        "dimensions": [dimension_payload(r) for r in spec["dimensions"]],
        "metrics": [metric_payload(r, keys, spec.get("headline")) for r in spec["metrics"]],
        "terms": [term_payload(r) for r in spec["terms"]],
    }


class Api:
    def __init__(self, base_url: str) -> None:
        self.base = base_url.rstrip("/")

    def call(self, method: str, path: str, body: dict | None = None, *, ok_statuses: tuple[int, ...] = (200,)) -> Any:
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(f"{self.base}{path}", data=data, method=method, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=300) as response:  # noqa: S310 - the Backend URL the operator passes
                return json.loads(response.read() or b"{}")
        except urllib.error.HTTPError as exc:
            text = exc.read().decode(errors="replace")[:1500]
            if exc.code in ok_statuses:
                return json.loads(text) if text.startswith("{") else {"detail": text}
            raise ApiError(f"{method} {path} -> HTTP {exc.code}: {text}") from exc
        except urllib.error.URLError as exc:
            raise ApiError(f"{method} {path} -> {exc.reason}") from exc


def pick_connector(api: Api, wanted: str | None) -> dict:
    connectors = api.call("GET", "/api/v1/connectors?connector_type=trino")["connectors"]
    if wanted:
        connectors = [c for c in connectors if c["id"] == wanted]
    if len(connectors) != 1:
        names = ", ".join(f"{c.get('name')} ({c['id']})" for c in connectors) or "none"
        raise ApiError(f"Expected exactly one Trino Data Source, found {len(connectors)}: {names}. Create it in Data Sources first, or pass --connector-id.")
    return connectors[0]


def new_draft(api: Api, spec: dict) -> tuple[str, str]:
    """The model (created when missing) and a fresh DRAFT version of it."""
    models = api.call("GET", "/api/v1/semantic/models")["models"]
    model = next((m for m in models if m["key"] == spec["key"]), None)
    if model is None:
        model = api.call("POST", "/api/v1/semantic/models", {"name": spec["name"], "key": spec["key"], "description": spec["description"]})["model"]
        versions = api.call("GET", f"/api/v1/semantic/models/{model['id']}/versions")["versions"]
        return model["id"], max(versions, key=lambda v: v["version_number"])["id"]
    version = api.call("POST", f"/api/v1/semantic/models/{model['id']}/versions")["version"]
    return model["id"], version["id"]


def default_base_url() -> str | None:
    sys.path.insert(0, str(HERE))
    import judge_answers  # noqa: PLC0415 - owns the Backend URL derivation inside Cloudera AI

    return judge_answers.default_base_url(dict(os.environ))


def main(spec: dict, argv: list[str] | None = None, *, doc: str = "") -> int:
    parser = argparse.ArgumentParser(description=(doc or __doc__).split("\n")[0])
    parser.add_argument("--base-url")
    parser.add_argument("--connector-id")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-publish", action="store_true")
    args = parser.parse_args(argv)

    if args.dry_run:
        body = plan(spec, "<trino data source id>")
        print(f"Model {spec['key']}: " + ", ".join(f"{len(v)} {k}" for k, v in body.items()))
        for metric in body["metrics"]:
            print(f"  [{metric['source_entity_key']}] {metric['name']}")
        return 0

    base_url = args.base_url or default_base_url()
    if not base_url:
        print("No Backend URL: run this in a Cloudera AI Session, or pass --base-url (with its secret path).", file=sys.stderr)
        return 2
    api = Api(base_url)
    try:
        connector = pick_connector(api, args.connector_id)
        print(f"Trino Data Source: {connector.get('name')}")
        model_id, version_id = new_draft(api, spec)
        print(f"Model {spec['key']}, new draft version {version_id}")
        body = plan(spec, connector["id"])
        for kind in ("entities", "dimensions", "metrics", "terms"):
            for item in body[kind]:
                api.call("POST", f"/api/v1/semantic/versions/{version_id}/{kind}", item)
            print(f"  created {len(body[kind])} {kind}")
        report = api.call("POST", f"/api/v1/semantic/versions/{version_id}/validate", {"mode": "full"})
        warnings = report.get("warnings") or []
        print(f"Validation: valid={report.get('valid')} errors={len(report.get('errors') or [])} warnings={len(warnings)}")
        for item in (report.get("errors") or [])[:10]:
            print("  ERROR:", json.dumps(item, default=str)[:400])
        for item in warnings[:5]:
            print("  warning:", item.get("message"))
        readiness = api.call("GET", f"/api/v1/semantic/versions/{version_id}/readiness")
        print("Readiness:", readiness.get("activation_readiness"))
        if args.no_publish:
            print("Not published (--no-publish). Review the draft in Semantic Layer.")
            return 0
        result = api.call("POST", f"/api/v1/semantic/models/{model_id}/publish-to-ask-data", {"version_id": version_id}, ok_statuses=(200, 422, 502))
        print("Publish:", json.dumps(result, default=str)[:900])
        status = str(result.get("status", "")).lower()
        return 0 if status not in {"needs_attention", "activation_failed"} and "detail" not in result else 1
    except ApiError as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        return 1

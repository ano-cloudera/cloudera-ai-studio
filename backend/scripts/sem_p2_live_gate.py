#!/usr/bin/env python3
"""Live API gates for SEMANTIC_LAYER_V2 Phase 2 extensions."""
from __future__ import annotations

import json
import sys

import httpx

BASE = "http://127.0.0.1:8001"


def main() -> int:
    results: dict[str, str] = {}
    client = httpx.Client(base_url=BASE, timeout=120.0)
    try:
        results["health"] = "PASS" if client.get("/health").status_code == 200 else "FAIL"
        models = client.get("/api/v1/semantic/models")
        results["models_list"] = "PASS" if models.status_code == 200 else "FAIL"
        rows = models.json().get("models") or [] if models.status_code == 200 else []
        if not rows:
            results["overview"] = "SKIP"
            results["entities_paginated"] = "SKIP"
            results["metrics_paginated"] = "SKIP"
        else:
            mid = rows[0]["id"]
            ov = client.get(f"/api/v1/semantic/models/{mid}/overview")
            results["overview"] = "PASS" if ov.status_code == 200 and "counts" in ov.json() else "FAIL"
            vers = client.get(f"/api/v1/semantic/models/{mid}/versions")
            versions = vers.json().get("versions") or [] if vers.status_code == 200 else []
            vid = next((v["id"] for v in versions if v.get("status") == "DRAFT"), None)
            if not vid and versions:
                vid = versions[0]["id"]
            if vid:
                ent = client.get(
                    f"/api/v1/semantic/versions/{vid}/entities",
                    params={"search": "a", "sort": "name", "order": "asc", "page": 1, "page_size": 5},
                )
                body = ent.json() if ent.status_code == 200 else {}
                results["entities_paginated"] = (
                    "PASS" if ent.status_code == 200 and "total" in body and "entities" in body else "FAIL"
                )
                met = client.get(
                    f"/api/v1/semantic/versions/{vid}/metrics",
                    params={"sort": "modified", "order": "desc", "page": 1, "page_size": 5},
                )
                mbody = met.json() if met.status_code == 200 else {}
                results["metrics_paginated"] = (
                    "PASS" if met.status_code == 200 and "total" in mbody and "metrics" in mbody else "FAIL"
                )
            else:
                results["entities_paginated"] = "SKIP"
                results["metrics_paginated"] = "SKIP"
        sug = client.post("/api/v1/semantic/suggestions", json={"connection_id": "00000000-0000-0000-0000-000000000001", "tables": []})
        results["suggestions_api"] = "PASS" if sug.status_code in (200, 400, 404, 422) else "FAIL"
        val = client.get("/api/v1/semantic/validators/health")
        results["model_health"] = "PASS" if val.status_code == 200 else "FAIL"
        if vid:
            dim = client.get(f"/api/v1/semantic/versions/{vid}/dimensions", params={"page": 1, "page_size": 5, "sort": "modified", "order": "desc"})
            results["dimensions_paginated"] = "PASS" if dim.status_code == 200 and "total" in dim.json() else "FAIL"
            rel = client.get(f"/api/v1/semantic/versions/{vid}/relationships", params={"search": "a", "page": 1, "page_size": 5})
            results["relationships_paginated"] = "PASS" if rel.status_code == 200 and "total" in rel.json() else "FAIL"
            terms = client.get(f"/api/v1/semantic/versions/{vid}/terms", params={"page": 1, "page_size": 5})
            results["glossary_paginated"] = "PASS" if terms.status_code == 200 and "total" in terms.json() else "FAIL"
            recent = client.get(f"/api/v1/semantic/versions/{vid}/recent-definitions", params={"page": 1, "page_size": 5, "type": "metric"})
            results["recent_definitions"] = "PASS" if recent.status_code == 200 and "definitions" in recent.json() else "FAIL"
            validate = client.post(
                f"/api/v1/semantic/versions/{vid}/metrics/validate",
                json={
                    "name": "Gate Metric",
                    "business_definition": "Check",
                    "expression": "SUM(missing_col)",
                    "aggregation": "sum",
                    "source_entity_key": "nonexistent_entity",
                },
            )
            vbody = validate.json() if validate.status_code == 200 else {}
            results["metric_validate"] = (
                "PASS" if validate.status_code == 200 and vbody.get("valid") is False and vbody.get("issues") else "FAIL"
            )
            bulk = client.post(f"/api/v1/semantic/versions/{vid}/metrics/bulk-delete", json={"ids": []})
            results["metrics_bulk_delete_route"] = "PASS" if bulk.status_code == 422 else "FAIL"
            draft_vid = next((v["id"] for v in versions if v.get("status") == "DRAFT"), None) if versions else None
            ent_vid = draft_vid or vid
            ents = client.get(f"/api/v1/semantic/versions/{ent_vid}/entities", params={"page_size": 1}).json().get("entities") or []
            if not draft_vid or not ents:
                results["glossary_related_mapping"] = "SKIP"
            else:
                import uuid as _uuid

                term = client.post(
                    f"/api/v1/semantic/versions/{draft_vid}/terms",
                    json={
                        "key": f"gate_term_{_uuid.uuid4().hex[:8]}",
                        "term": "Gate Term",
                        "related_entity_keys": [ents[0]["key"]],
                    },
                )
                results["glossary_related_mapping"] = "PASS" if term.status_code == 200 else "FAIL"
        else:
            results["dimensions_paginated"] = "SKIP"
            results["relationships_paginated"] = "SKIP"
            results["glossary_paginated"] = "SKIP"
            results["recent_definitions"] = "SKIP"
            results["metric_validate"] = "SKIP"
            results["metrics_bulk_delete_route"] = "SKIP"
            results["glossary_related_mapping"] = "SKIP"
    finally:
        client.close()
    print(json.dumps(results, indent=2))
    failed = [k for k, v in results.items() if v == "FAIL"]
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

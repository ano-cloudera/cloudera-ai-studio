#!/usr/bin/env python3
"""Safe reset of Golden Banking demo assets only (non-destructive by default)."""
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
API = os.environ.get("GOLDEN_PATH_API_BASE", "http://127.0.0.1:8001")

from golden_banking_knowledge_constants import LIBRARY_NAME  # noqa: E402
from golden_banking_semantic_constants import MODEL_KEY, MODEL_NAME  # noqa: E402
from golden_e2e_common import GOLDEN_PROMPT_KEY, GOLDEN_SKILL_KEY  # noqa: E402

CONNECTOR_KEY = os.environ.get("BANKING_CONNECTOR_KEY", "golden_banking_pg")

REMOVES = """
When --apply and GOLDEN_RESET_CONFIRM=1:

- Knowledge library named: Retail Banking Knowledge (DELETE library API)
- Connector key: golden_banking_pg (DELETE connector API)

Listed but not deleted (no destructive API today):

- Prompt key golden_banking_executive_summary
- Skill key golden_banking_analyst
- Semantic model retail_banking_analytics (re-register via bootstrap instead)

Does NOT remove: global/system prompts, unrelated libraries, AI Model Registry,
unrelated connectors, SQLite file, Qdrant collections wholesale, or CAI sim root.
"""


def _http(method: str, path: str, body: dict | None = None) -> tuple[int, dict | str]:
    data = None if body is None else json.dumps(body).encode()
    headers = {"Content-Type": "application/json"} if body else {}
    req = urllib.request.Request(API + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            raw = resp.read().decode()
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except json.JSONDecodeError:
            return e.code, raw


def _find_by_key(collection: str, key: str) -> dict | None:
    st, body = _http("GET", f"/api/v1/{collection}")
    if st != 200 or not isinstance(body, dict):
        return None
    plural = {"prompts": "prompts", "skills": "skills", "connectors": "connectors"}.get(collection, collection)
    for row in body.get(plural) or []:
        if row.get("key") == key:
            return row
    return None


def _find_semantic_model() -> dict | None:
    st, body = _http("GET", "/api/v1/semantic/models")
    if st != 200 or not isinstance(body, dict):
        return None
    for row in body.get("models") or []:
        if row.get("key") == MODEL_KEY or row.get("name") == MODEL_NAME:
            return row
    return None


def _find_library() -> dict | None:
    page = 1
    while page <= 20:
        st, body = _http("GET", f"/api/v1/libraries?page={page}&page_size=100")
        if st != 200 or not isinstance(body, dict):
            return None
        for item in body.get("items") or []:
            if item.get("name") == LIBRARY_NAME:
                return item
        total = int(body.get("total") or 0)
        if page * 100 >= total:
            break
        page += 1
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Reset Golden Banking demo assets")
    parser.add_argument("--dry-run", action="store_true", help="List assets that would be removed")
    parser.add_argument("--apply", action="store_true", help="Perform removal (requires GOLDEN_RESET_CONFIRM=1)")
    args = parser.parse_args()

    targets = {
        "prompt": _find_by_key("prompts", GOLDEN_PROMPT_KEY),
        "skill": _find_by_key("skills", GOLDEN_SKILL_KEY),
        "library": _find_library(),
        "semantic_model": _find_semantic_model(),
        "connector": _find_by_key("connectors", CONNECTOR_KEY),
    }
    report = {"targets": {k: (v.get("id") if v else None) for k, v in targets.items()}, "policy": REMOVES.strip()}

    if args.dry_run or not args.apply:
        print(json.dumps(report, indent=2))
        print(REMOVES)
        return 0

    if os.environ.get("GOLDEN_RESET_CONFIRM") != "1":
        print("Refusing --apply without GOLDEN_RESET_CONFIRM=1", file=sys.stderr)
        return 1

    actions: list[dict] = []
    if targets["library"]:
        st, _ = _http("DELETE", f"/api/v1/libraries/{targets['library']['id']}")
        actions.append({"library": st})
    if targets["connector"]:
        st, _ = _http("DELETE", f"/api/v1/connectors/{targets['connector']['id']}")
        actions.append({"connector": st})

    out_path = ROOT / "testing/evidence/golden-path/FULL-E2E/golden-reset.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({"actions": actions, "targets": report["targets"]}, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "actions": actions}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

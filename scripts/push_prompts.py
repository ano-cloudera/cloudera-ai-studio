"""Put the prompts in backend/prompts into the platform through the Backend API (stdlib only), so they can be tuned without a redeploy.

The Prompts feature (Prompts page, /api/v1/prompts) keeps a prompt per key and scope with versions; what applies is the first of
project, workspace, global override, then the file in backend/prompts. This script makes the file's text the active version of a
key at one scope (default global): a new version is added and published, the old one stays in the version history and can be rolled
back from the Prompts page. A prompt whose active text already equals the file is left alone.

    python scripts/push_prompts.py --status                 # which prompt applies for each key now, and whether it differs from the file
    python scripts/push_prompts.py --dry-run                # what would be pushed
    python scripts/push_prompts.py                          # push every key that has a file
    python scripts/push_prompts.py --key rag.system         # one key
    python scripts/push_prompts.py --scope workspace        # at one scope (default: auto)

With the default --scope auto, a key is pushed to the scope that applies to it now (so a workspace prompt is updated, not shadowed by
a new global one); a key with no prompt in the platform yet is created at global. The Prompts API has no delete: a prompt left at
another scope stays, harmless while it holds the same text, and --status says which scopes hold a key.

It runs in a Cloudera AI Session (the Backend URL is derived the way the deploy Job does it); pass --base-url to use another one.
Nothing secret is printed: only keys, scopes, version numbers and sizes.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PROMPT_DIR = ROOT / "backend" / "prompts"

# The keys that have a file in backend/prompts (the Prompts feature knows ask_data.system, rag.system and rag.insufficient_evidence;
# the last one is a built-in text, not a file).
FILES: dict[str, str] = {
    "ask_data.system": "global_system.md",
    "rag.system": "rag_system.txt",
    "ask_data.analyst": "result_analyst.md",
    "ask_data.agent": "agent_tools.md",
    "ask_data.agent_report": "agent_tool_report.md",
    "ask_data.turn_reader": "conversation_rewrite.md",
}
NAMES: dict[str, str] = {
    "ask_data.system": "Ask Data system prompt",
    "rag.system": "Documents system prompt",
    "ask_data.analyst": "Data answer writer",
    "ask_data.agent": "Analyst agent: how it investigates",
    "ask_data.agent_report": "Analyst agent: the report it writes",
    "ask_data.turn_reader": "Question reader: data or analysis",
}


def _api(base_url: str):
    sys.path.insert(0, str(HERE))
    from semantic_api import Api  # noqa: PLC0415 - the same stdlib client the semantic model script uses

    return Api(base_url)


def _in_session() -> bool:
    """Whether a Backend URL can be derived here (inside a Cloudera AI Session), so a dry run can ask the platform what would change."""
    sys.path.insert(0, str(HERE))
    try:
        import semantic_api  # noqa: PLC0415

        return bool(semantic_api.default_base_url())
    except Exception:  # noqa: BLE001
        return False


def _same(a: str, b: str) -> bool:
    return a.strip().replace("\r\n", "\n") == b.strip().replace("\r\n", "\n")


def _versions(api, prompt_id: str) -> list[dict]:
    return api.call("GET", f"/api/v1/prompts/{prompt_id}/versions")["versions"]


def _find(api, key: str, scope: str) -> dict | None:
    rows = api.call("GET", f"/api/v1/prompts?scope={scope}")["prompts"]
    return next((row for row in rows if row["key"] == key and row["scope"] == scope), None)


SPECIFICITY = {"file": 0, "global": 1, "workspace": 2, "project": 3}  # the more specific one applies


def status(api, key: str, text: str, pushed_scope: str | None = None) -> str:
    effective = api.call("POST", "/api/v1/prompts/resolve", {"prompt_key": key})
    layers = effective.get("layers", [])
    shown = ", ".join(f"{layer['scope']} v{layer['version_number']}" for layer in layers) or "none"
    equal = _same(effective.get("content", ""), text)
    line = f"{key}: applies from {effective.get('source_label')} (layers: {shown}); {'same as the file' if equal else 'DIFFERENT from the file'}"
    source = effective.get("source", "file")
    if pushed_scope and SPECIFICITY.get(source, 0) > SPECIFICITY[pushed_scope]:
        line += f"\n  WARNING: a {source} prompt overrides what was pushed at {pushed_scope}; update or delete it in Prompts, or push with --scope {source}"
    elif len(layers) > 1:
        line += f"\n  NOTE: {len(layers)} scopes hold this key ({', '.join(layer['scope'] for layer in layers)}); only the most specific applies"
    return line


def target_scope(api, key: str, requested: str) -> str:
    """The scope to write: the one asked for, or with `auto` the scope of the prompt that applies now (global when only the file does)."""
    if requested != "auto":
        return requested
    source = api.call("POST", "/api/v1/prompts/resolve", {"prompt_key": key}).get("source", "file")
    return source if source in ("project", "workspace", "global") else "global"


def push(api, key: str, text: str, scope: str, *, dry_run: bool) -> str:
    row = _find(api, key, scope)
    if row is not None:
        versions = _versions(api, row["id"])
        active = next((v for v in versions if v["status"] == "ACTIVE"), None)
        if active is not None and _same(active["content"], text):
            return f"{key} ({scope}): already active as version {active['version_number']}, nothing to do"
        if dry_run:
            return f"{key} ({scope}): would add version {(versions[0]['version_number'] if versions else 0) + 1} ({len(text)} characters) and publish it"
        version = api.call("POST", f"/api/v1/prompts/{row['id']}/versions", {"content": text, "created_by": "push_prompts.py"})["version"]
        api.call("POST", f"/api/v1/prompts/{row['id']}/versions/{version['id']}/publish")
        return f"{key} ({scope}): published version {version['version_number']} ({len(text)} characters); the earlier one stays in the history"
    if dry_run:
        return f"{key} ({scope}): would create the prompt with this text ({len(text)} characters) and publish it"
    created = api.call("POST", "/api/v1/prompts", {"name": NAMES.get(key, key), "key": key, "scope": scope, "description": "From backend/prompts, pushed by scripts/push_prompts.py", "initial_content": text})["prompt"]
    first = _versions(api, created["id"])[0]
    api.call("POST", f"/api/v1/prompts/{created['id']}/versions/{first['id']}/publish")
    return f"{key} ({scope}): created and published version {first['version_number']} ({len(text)} characters)"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    parser.add_argument("--base-url")
    parser.add_argument("--key", action="append", choices=sorted(FILES), help="a key to push (repeat); default: every key with a file")
    parser.add_argument("--scope", default="auto", choices=["auto", "global", "workspace", "project"])
    parser.add_argument("--status", action="store_true", help="only show which prompt applies and whether it differs from the file")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    keys = args.key or sorted(FILES)
    texts = {key: (PROMPT_DIR / FILES[key]).read_text(encoding="utf-8") for key in keys}

    if args.dry_run and not args.status and not args.base_url and not _in_session():
        for key in keys:
            print(f"{key} ({args.scope}): would push {FILES[key]} ({len(texts[key])} characters)")
        return 0

    base_url = args.base_url
    if not base_url:
        sys.path.insert(0, str(HERE))
        import semantic_api  # noqa: PLC0415

        base_url = semantic_api.default_base_url()
    if not base_url:
        print("No Backend URL: run this in a Cloudera AI Session, or pass --base-url (with its secret path).", file=sys.stderr)
        return 2
    api = _api(base_url)
    try:
        scopes = {key: target_scope(api, key, args.scope) for key in keys}
        for key in keys:
            print(status(api, key, texts[key]) if args.status else push(api, key, texts[key], scopes[key], dry_run=args.dry_run))
        if not args.status and not args.dry_run:
            print()
            for key in keys:
                print(status(api, key, texts[key], scopes[key]))
    except RuntimeError as exc:  # semantic_api.ApiError
        print(f"Failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

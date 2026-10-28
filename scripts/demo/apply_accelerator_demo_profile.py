#!/usr/bin/env python3
"""Apply AMP demo profile (starters + presentation + optional hero semantic pin) to workspace Ask Data settings."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "demo"))

from golden_e2e_common import EVIDENCE, http  # noqa: E402

PRESET_PATH = ROOT / "config/examples/accelerator-demo-presentation.json"
PRESET_META_KEYS = frozenset({"description", "hero_semantic_model_key", "hero_semantic_model_keys"})


def _load_preset(path: Path) -> tuple[dict, list[str]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    hero_keys: list[str] = []
    for meta in ("hero_semantic_model_keys", "hero_semantic_model_key"):
        val = raw.get(meta)
        if isinstance(val, str) and val.strip():
            hero_keys.append(val.strip())
        elif isinstance(val, list):
            hero_keys.extend(str(x).strip() for x in val if str(x).strip())
    env_key = (os.environ.get("AMP_HERO_SEMANTIC_MODEL_KEY") or "").strip()
    if env_key:
        hero_keys.insert(0, env_key)
    preset = {k: v for k, v in raw.items() if k not in PRESET_META_KEYS}
    if preset.get("default_semantic_model_id") in (None, ""):
        preset.pop("default_semantic_model_id", None)
    # dedupe keys, preserve order
    seen: set[str] = set()
    ordered_keys: list[str] = []
    for k in hero_keys:
        if k not in seen:
            seen.add(k)
            ordered_keys.append(k)
    return preset, ordered_keys


def _published_models() -> list[dict[str, Any]]:
    st, body = http("GET", "/api/v1/semantic/models")
    if st != 200 or not isinstance(body, dict):
        return []
    out: list[dict[str, Any]] = []
    for m in body.get("models") or []:
        if m.get("active_version_id"):
            out.append(m)
    return out


def _resolve_hero_model_id(hero_keys: list[str]) -> tuple[str | None, str | None]:
    published = _published_models()
    if not published:
        return None, "no published semantic models"
    for key in hero_keys:
        for m in published:
            if m.get("key") == key:
                return str(m["id"]), None
    if len(published) == 1:
        m = published[0]
        return str(m["id"]), f"sole published model {m.get('key')!r}"
    keys_present = [str(m.get("key")) for m in published]
    return None, f"multiple published models {keys_present}; set hero_semantic_model_key in preset or pin in Settings"


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply accelerator demo Ask Data profile")
    parser.add_argument("--workspace", default="default", help="Workspace slug (default: default)")
    parser.add_argument(
        "--preset",
        type=Path,
        default=PRESET_PATH,
        help="JSON preset path",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print merged settings only")
    parser.add_argument(
        "--skip-pin",
        action="store_true",
        help="Do not set default_semantic_model_id from hero_semantic_model_key / sole published model",
    )
    args = parser.parse_args()

    if not args.preset.is_file():
        print(f"preset not found: {args.preset}", file=sys.stderr)
        return 1

    preset, hero_keys = _load_preset(args.preset)
    st, current = http("GET", f"/api/v1/ask-data/settings?workspace_slug={args.workspace}")
    if st != 200 or not isinstance(current, dict):
        print(f"GET settings failed: {st} {current}", file=sys.stderr)
        return 1

    merged = dict(current.get("settings") or {})
    merged.update(preset)
    pin_note: str | None = None
    if not args.skip_pin and not (merged.get("default_semantic_model_id") or "").strip():
        hero_id, pin_note = _resolve_hero_model_id(hero_keys)
        if hero_id:
            merged["default_semantic_model_id"] = hero_id
    if args.dry_run:
        print(
            json.dumps(
                {"workspace_slug": args.workspace, "settings": merged, "pin_note": pin_note},
                indent=2,
            )
        )
        return 0

    st, body = http(
        "PUT",
        f"/api/v1/ask-data/settings?workspace_slug={args.workspace}",
        merged,
    )
    if st != 200:
        print(f"PUT settings failed: {st} {body}", file=sys.stderr)
        return 1

    out_dir = EVIDENCE.parent / "AMP-READINESS"
    out_dir.mkdir(parents=True, exist_ok=True)
    artifact = {
        "workspace_slug": args.workspace,
        "preset": str(args.preset),
        "hero_semantic_model_keys": hero_keys,
        "pin_note": pin_note,
        "settings": body.get("settings") if isinstance(body, dict) else merged,
    }
    (out_dir / "demo-profile-applied.json").write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")
    out: dict[str, Any] = {"ok": True, "workspace_slug": args.workspace}
    if pin_note:
        out["pin_note"] = pin_note
    if merged.get("default_semantic_model_id"):
        out["default_semantic_model_id"] = merged["default_semantic_model_id"]
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

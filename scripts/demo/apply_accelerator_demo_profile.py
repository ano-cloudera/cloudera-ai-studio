#!/usr/bin/env python3
"""Apply AMP / Golden Banking demo profile (starters + presentation) to workspace Ask Data settings."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "demo"))

from golden_e2e_common import EVIDENCE, http  # noqa: E402

PRESET_PATH = ROOT / "config/examples/accelerator-demo-presentation.json"


def _load_preset(path: Path) -> dict:
    raw = json.loads(path.read_text(encoding="utf-8"))
    preset = {k: v for k, v in raw.items() if k != "description"}
    return preset


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
    args = parser.parse_args()

    if not args.preset.is_file():
        print(f"preset not found: {args.preset}", file=sys.stderr)
        return 1

    preset = _load_preset(args.preset)
    st, current = http("GET", f"/api/v1/ask-data/settings?workspace_slug={args.workspace}")
    if st != 200 or not isinstance(current, dict):
        print(f"GET settings failed: {st} {current}", file=sys.stderr)
        return 1

    merged = dict(current.get("settings") or {})
    merged.update(preset)
    if args.dry_run:
        print(json.dumps({"workspace_slug": args.workspace, "settings": merged}, indent=2))
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
        "settings": body.get("settings") if isinstance(body, dict) else merged,
    }
    (out_dir / "demo-profile-applied.json").write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "workspace_slug": args.workspace}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

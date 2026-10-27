#!/usr/bin/env python3
"""Merge latest per-domain uat_domain_5x5_run_*.json files into one summary."""
from __future__ import annotations

import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
EVAL = BACKEND / "eval"


def main() -> int:
    paths = sorted(EVAL.glob("uat_domain_5x5_run_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not paths:
        print("No reports found", file=sys.stderr)
        return 1
    seen_domains: set[str] = set()
    merged_domains: list[dict] = []
    for path in paths:
        data = json.loads(path.read_text(encoding="utf-8"))
        for block in data.get("by_domain") or []:
            dom = block.get("domain")
            if dom in seen_domains:
                continue
            seen_domains.add(dom)
            merged_domains.append(block)
        if len(seen_domains) >= 10:
            break
    total = sum(b.get("total", 0) for b in merged_domains)
    passed = sum(b.get("passed", 0) for b in merged_domains)
    out = EVAL / "uat_domain_5x5_merged_latest.json"
    payload = {
        "merged_from": [str(p) for p in paths[:15]],
        "passed": passed,
        "total": total,
        "by_domain": sorted(merged_domains, key=lambda b: b.get("domain") or ""),
    }
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"report": str(out), "passed": passed, "total": total}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

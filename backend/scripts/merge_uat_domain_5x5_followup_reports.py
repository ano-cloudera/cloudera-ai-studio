#!/usr/bin/env python3
"""Merge uat_domain_5x5_followup_run_*.json files into one summary."""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
EVAL = BACKEND / "eval"


def main() -> int:
    paths = sorted(EVAL.glob("uat_domain_5x5_followup_run_*.json"), key=lambda p: p.stat().st_mtime)
    if len(sys.argv) > 1:
        paths = [Path(p) for p in sys.argv[1:]]
    if not paths:
        print("No reports found", file=sys.stderr)
        return 1

    by_domain: dict[str, list] = defaultdict(list)
    turns_passed = turns_total = scenarios_passed = scenarios_total = 0
    judge_passed = judge_total = 0
    base_url = provider = None
    judge_enabled = None

    # Latest file wins per scenario id (for reruns).
    scen_latest: dict[str, tuple[float, dict]] = {}

    for path in paths:
        data = json.loads(path.read_text(encoding="utf-8"))
        base_url = base_url or data.get("base_url")
        provider = provider or data.get("provider")
        judge_enabled = data.get("judge_enabled")
        mtime = path.stat().st_mtime
        for block in data.get("by_domain") or []:
            dom = str(block.get("domain") or "unknown")
            for scen in block.get("scenarios") or []:
                sid = str(scen.get("id") or "")
                key = f"{dom}:{sid}"
                row = {**scen, "domain": dom, "_source_report": str(path.name)}
                prev = scen_latest.get(key)
                if prev is None or mtime >= prev[0]:
                    scen_latest[key] = (mtime, row)

    for _mtime, row in scen_latest.values():
        dom = str(row.get("domain") or "unknown")
        by_domain[dom].append(row)

    for items in by_domain.values():
        for scen in items:
            scenarios_total += 1
            if scen.get("pass"):
                scenarios_passed += 1
            for turn in scen.get("turns") or []:
                turns_total += 1
                if turn.get("pass"):
                    turns_passed += 1
                jb = turn.get("judge") if isinstance(turn.get("judge"), dict) else None
                if jb is not None:
                    judge_total += 1
                    if jb.get("acceptable"):
                        judge_passed += 1
                elif turn.get("judge_error"):
                    judge_total += 1

    domain_summary = []
    for dom in sorted(by_domain.keys()):
        items = by_domain[dom]
        d_pass = sum(1 for i in items if i.get("pass"))
        domain_summary.append({"domain": dom, "scenarios_passed": d_pass, "scenarios_total": len(items), "scenarios": items})

    out = EVAL / "uat_domain_5x5_followup_merged_latest.json"
    payload = {
        "merged_from": [str(p.name) for p in paths],
        "base_url": base_url,
        "provider": provider,
        "judge_enabled": judge_enabled,
        "scenarios_passed": scenarios_passed,
        "scenarios_total": scenarios_total,
        "turns_passed": turns_passed,
        "turns_total": turns_total,
        "judge_passed": judge_passed,
        "judge_total": judge_total,
        "by_domain": domain_summary,
    }
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"report": str(out), "scenarios_passed": scenarios_passed, "scenarios_total": scenarios_total}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Show what the judge saw for some turns of a judge run: the failed checks, the steps the agent took and the full answer.

    python scripts/judge_show.py /home/cdsw/j_demo.json 4 8        # turns 4 and 8
    python scripts/judge_show.py /home/cdsw/j_demo.json             # every failed turn

Reads the file written by scripts/judge_answers.py --out; prints nothing secret.
"""
from __future__ import annotations

import json
import sys


def turns_of(data: dict) -> list[dict]:
    if "turns" in data:
        return data["turns"]
    return [turn for run in data.get("results", []) for turn in run.get("turns", [])]


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    data = json.load(open(argv[0], encoding="utf-8"))
    wanted = {int(n) for n in argv[1:]}
    for turn in turns_of(data):
        if (wanted and turn.get("turn") not in wanted) or (not wanted and turn.get("passed")):
            continue
        print("=" * 100)
        print(f"{turn.get('turn')}. {turn.get('question')}  [{turn.get('strategy')}, {turn.get('seconds')}s]")
        for failed in turn.get("failed") or []:
            print(f"  FAILED {failed.get('check')}: {failed.get('seen')}")
        print("  STEPS:")
        for step in turn.get("steps") or []:
            print(f"    {step}")
        print("  ANSWER:")
        print("    " + (turn.get("answer") or "").replace("\n", "\n    "))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

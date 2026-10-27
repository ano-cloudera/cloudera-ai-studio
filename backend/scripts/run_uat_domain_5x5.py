#!/usr/bin/env python3
"""Run 5×domain UAT matrix with mechanical checks + Gemini answer judge."""
from __future__ import annotations

import asyncio
import json
import sys
import uuid
from collections import defaultdict
from pathlib import Path
from typing import Any

BACKEND = Path(__file__).resolve().parents[1]
_REPO_VENV = BACKEND.parent / ".venv" / "bin" / "python"
if _REPO_VENV.is_file() and Path(sys.executable).resolve() != _REPO_VENV.resolve():
    import os

    os.execv(str(_REPO_VENV), [str(_REPO_VENV), *sys.argv])

import httpx
import yaml

sys.path.insert(0, str(BACKEND))

from eval.uat_answer_judge import compact_chat_response, judge_management_turn  # noqa: E402

BASE = "http://127.0.0.1:8000"
PROVIDER = "gemini"
SKIP_JUDGE = False
DOMAIN_FILTER: str | None = None
TIMEOUT = 360.0


def _parse_argv() -> None:
    global BASE, PROVIDER, SKIP_JUDGE, DOMAIN_FILTER
    args = [a for a in sys.argv[1:] if a.startswith("-")]
    pos = [a for a in sys.argv[1:] if not a.startswith("-")]
    if "--skip-judge" in args:
        SKIP_JUDGE = True
    for arg in args:
        if arg.startswith("--domain="):
            DOMAIN_FILTER = arg.split("=", 1)[1].strip()
    if len(pos) > 0:
        BASE = pos[0]
    if len(pos) > 1:
        PROVIDER = pos[1]


def check_case(body: dict, expect: dict) -> tuple[bool, str]:
    status = body.get("status")
    strategy = body.get("strategy")
    rows = int((body.get("data") or {}).get("row_count") or 0)
    allowed_status = expect.get("status")
    if isinstance(allowed_status, list):
        if status not in allowed_status:
            return False, f"status want one of {allowed_status} got {status}"
    elif allowed_status and status != allowed_status:
        return False, f"status want {allowed_status} got {status}"
    allowed_strategy = expect.get("strategy")
    if isinstance(allowed_strategy, list):
        if strategy not in allowed_strategy:
            return False, f"strategy want one of {allowed_strategy} got {strategy}"
    elif allowed_strategy and strategy != allowed_strategy:
        return False, f"strategy want {allowed_strategy} got {strategy}"
    min_rows = expect.get("min_rows")
    if min_rows is not None and status == "SUCCESS" and rows < int(min_rows):
        return False, f"row_count {rows} < min_rows {min_rows}"
    return True, "ok"


async def main() -> int:
    _parse_argv()
    path = BACKEND / "eval" / "uat_domain_5x5.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    cases = list(data.get("cases") or [])
    if DOMAIN_FILTER:
        cases = [c for c in cases if c.get("domain") == DOMAIN_FILTER]

    async with httpx.AsyncClient(base_url=BASE.rstrip("/"), timeout=TIMEOUT) as client:
        health = await client.get("/health")
        health.raise_for_status()
        models = (await client.get("/models")).json()
        model = ""
        for item in models.get("models") or []:
            if item.get("provider") == PROVIDER and item.get("available"):
                model = str(item.get("id") or "")
                break
        if not model:
            print("No available model for", PROVIDER, file=sys.stderr)
            return 1

        by_domain: dict[str, list[dict]] = defaultdict(list)
        passed = 0
        total = 0
        judge_passed = 0
        judge_total = 0

        for case in cases:
            total += 1
            cid = case["id"]
            domain = str(case.get("domain") or "unknown")
            q = case["question"]
            expect = case.get("expect") or {}
            judge_block = case.get("judge") if isinstance(case.get("judge"), dict) else {}
            min_score = int(judge_block.get("min_score") or 7)
            extra = list(judge_block.get("criteria") or [])
            extra.insert(0, f"Domain UAT bucket: {domain} — {data.get('scope', '')}")

            r = await client.post(
                "/chat",
                json={
                    "session_id": f"uat-5x5-{cid}-{uuid.uuid4().hex[:8]}",
                    "question": q,
                    "provider": PROVIDER,
                    "model": model,
                },
            )
            r.raise_for_status()
            body = r.json()
            mech_ok, note = check_case(body, expect)
            turn_ok = mech_ok
            verdict_payload = None
            judge_error = None

            if not SKIP_JUDGE:
                judge_total += 1
                verdict, judge_error = await judge_management_turn(
                    question=q,
                    response=body,
                    scenario_title=f"{domain} / {cid}",
                    turn_index=1,
                    prior_turns=None,
                    extra_criteria=extra,
                    min_score=min_score,
                    judge_provider=PROVIDER,
                )
                if verdict is not None:
                    verdict_payload = verdict.model_dump()
                    if verdict.acceptable:
                        judge_passed += 1
                    else:
                        turn_ok = False
                        note = f"judge score={verdict.score}: {verdict.summary[:100]}"
                elif judge_error:
                    turn_ok = False
                    note = f"judge_unavailable: {judge_error}"

            if turn_ok:
                passed += 1

            entry = {
                "id": cid,
                "domain": domain,
                "question": q,
                "pass": turn_ok,
                "mechanical_pass": mech_ok,
                "note": note,
                "status": body.get("status"),
                "strategy": body.get("strategy"),
                "row_count": (body.get("data") or {}).get("row_count"),
                "request_id": body.get("request_id"),
                "judge": verdict_payload,
                "judge_error": judge_error,
            }
            by_domain[domain].append(entry)
            mark = "OK" if turn_ok else "FAIL"
            jb = ""
            if verdict_payload:
                jb = f" judge={verdict_payload.get('score')}/10"
            print(f"{mark} [{domain}] {cid}: {body.get('status')} rows={(body.get('data') or {}).get('row_count')} {note}{jb}")

        domain_summary = []
        for dom, items in sorted(by_domain.items()):
            d_pass = sum(1 for i in items if i.get("pass"))
            domain_summary.append({"domain": dom, "passed": d_pass, "total": len(items), "cases": items})

        out = BACKEND / "eval" / f"uat_domain_5x5_run_{uuid.uuid4().hex[:8]}.json"
        payload = {
            "base_url": BASE,
            "provider": PROVIDER,
            "judge_enabled": not SKIP_JUDGE,
            "passed": passed,
            "total": total,
            "judge_passed": judge_passed,
            "judge_total": judge_total,
            "by_domain": domain_summary,
        }
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"report": str(out), "passed": passed, "total": total, "judge_passed": judge_passed}, indent=2))
        return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

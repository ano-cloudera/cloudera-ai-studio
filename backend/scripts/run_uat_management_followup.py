#!/usr/bin/env python3
"""Run management UAT scenarios with shared session (follow-up turns).

Mechanical checks (status/strategy/rows) plus optional Gemini answer judge.
Usage:
  python scripts/run_uat_management_followup.py [base_url] [provider] [--skip-judge]
"""
from __future__ import annotations

import asyncio
import json
import sys
import uuid
from pathlib import Path
from typing import Any

import httpx
import yaml

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from eval.uat_answer_judge import compact_chat_response, judge_management_turn  # noqa: E402

BASE = "http://127.0.0.1:8000"
PROVIDER = "gemini"
SKIP_JUDGE = False
TIMEOUT = 360.0


def _parse_argv() -> None:
    global BASE, PROVIDER, SKIP_JUDGE
    args = [a for a in sys.argv[1:] if a.startswith("-")]
    pos = [a for a in sys.argv[1:] if not a.startswith("-")]
    if "--skip-judge" in args:
        SKIP_JUDGE = True
    if len(pos) > 0:
        BASE = pos[0]
    if len(pos) > 1:
        PROVIDER = pos[1]


def check_turn(body: dict, expect: dict) -> tuple[bool, str]:
    status = body.get("status")
    strategy = body.get("strategy")
    rows = int((body.get("data") or {}).get("row_count") or 0)
    if expect.get("status") and status != expect["status"]:
        return False, f"status want {expect['status']} got {status}"
    if expect.get("strategy") and strategy != expect["strategy"]:
        return False, f"strategy want {expect['strategy']} got {strategy}"
    min_rows = expect.get("min_rows")
    if min_rows is not None and status == "SUCCESS" and rows < int(min_rows):
        return False, f"row_count {rows} < min_rows {min_rows}"
    return True, "ok"


def _judge_config(turn: dict, scenario: dict) -> dict[str, Any]:
    block = turn.get("judge") or scenario.get("judge") or {}
    if not isinstance(block, dict):
        return {}
    return block


async def main() -> int:
    _parse_argv()
    path = BACKEND / "eval" / "uat_management_followup.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    scenarios = list(data.get("scenarios") or [])

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

        summary: list[dict] = []
        passed = 0
        total = 0
        judge_passed = 0
        judge_total = 0

        for scenario in scenarios:
            sid = f"uat-mgmt-{scenario['id']}-{uuid.uuid4().hex[:8]}"
            scen_ok = True
            turn_results: list[dict] = []
            prior_for_judge: list[dict[str, Any]] = []

            for index, turn in enumerate(scenario.get("turns") or []):
                total += 1
                q = turn["question"]
                expect = turn.get("expect") or {}
                r = await client.post(
                    "/chat",
                    json={
                        "session_id": sid,
                        "question": q,
                        "provider": PROVIDER,
                        "model": model,
                    },
                )
                r.raise_for_status()
                body = r.json()
                mech_ok, note = check_turn(body, expect)
                turn_ok = mech_ok

                judge_block = _judge_config(turn, scenario)
                min_score = int(judge_block.get("min_score") or 7)
                extra_criteria = list(judge_block.get("criteria") or [])
                verdict_payload: dict[str, Any] | None = None
                judge_error: str | None = None

                if not SKIP_JUDGE:
                    judge_total += 1
                    verdict, judge_error = await judge_management_turn(
                        question=q,
                        response=body,
                        scenario_title=str(scenario.get("title") or scenario["id"]),
                        turn_index=index + 1,
                        prior_turns=prior_for_judge,
                        extra_criteria=extra_criteria or None,
                        min_score=min_score,
                        judge_provider=PROVIDER,
                    )
                    if verdict is not None:
                        verdict_payload = verdict.model_dump()
                        if verdict.acceptable:
                            judge_passed += 1
                        else:
                            turn_ok = False
                            note = f"judge: score={verdict.score} — {verdict.summary[:120]}"
                    elif judge_error:
                        turn_ok = False
                        note = f"judge_unavailable: {judge_error}"

                if not turn_ok:
                    scen_ok = False
                if turn_ok:
                    passed += 1

                prior_for_judge.append(
                    {
                        "question": q,
                        "compact_response": compact_chat_response(body),
                    }
                )

                turn_results.append(
                    {
                        "turn": index + 1,
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
                )
                mark = "OK" if turn_ok else "FAIL"
                judge_bit = ""
                if verdict_payload:
                    judge_bit = f" judge={verdict_payload.get('score')}/10 acceptable={verdict_payload.get('acceptable')}"
                print(
                    f"{mark} [{scenario['id']}] turn {index + 1}: {body.get('status')} "
                    f"rows={(body.get('data') or {}).get('row_count')} {note}{judge_bit}"
                )

            summary.append(
                {
                    "id": scenario["id"],
                    "title": scenario.get("title"),
                    "session_id": sid,
                    "pass": scen_ok,
                    "turns": turn_results,
                }
            )

        out = BACKEND / "eval" / f"uat_management_run_{uuid.uuid4().hex[:8]}.json"
        payload = {
            "base_url": BASE,
            "provider": PROVIDER,
            "judge_enabled": not SKIP_JUDGE,
            "passed": passed,
            "total": total,
            "judge_passed": judge_passed,
            "judge_total": judge_total,
            "scenarios": summary,
        }
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(
            json.dumps(
                {
                    "report": str(out),
                    "passed": passed,
                    "total": total,
                    "judge_passed": judge_passed,
                    "judge_total": judge_total,
                },
                indent=2,
            )
        )
        return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

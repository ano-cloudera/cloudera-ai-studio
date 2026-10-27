#!/usr/bin/env python3
"""Run 5×domain follow-up UAT (2 turns per scenario, shared session_id)."""
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
YAML_NAME = "uat_domain_5x5_followup.yaml"
TIMEOUT = 360.0


def _parse_argv() -> None:
    global BASE, PROVIDER, SKIP_JUDGE, DOMAIN_FILTER, YAML_NAME
    args = [a for a in sys.argv[1:] if a.startswith("-")]
    pos = [a for a in sys.argv[1:] if not a.startswith("-")]
    if "--skip-judge" in args:
        SKIP_JUDGE = True
    for arg in args:
        if arg.startswith("--domain="):
            DOMAIN_FILTER = arg.split("=", 1)[1].strip()
        if arg.startswith("--yaml="):
            YAML_NAME = arg.split("=", 1)[1].strip()
    if len(pos) > 0:
        BASE = pos[0]
    if len(pos) > 1:
        PROVIDER = pos[1]


def check_turn(body: dict, expect: dict) -> tuple[bool, str]:
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
    path = BACKEND / "eval" / YAML_NAME
    if not path.is_file():
        print(f"YAML not found: {path}", file=sys.stderr)
        return 1
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    scenarios = list(data.get("scenarios") or [])
    if DOMAIN_FILTER:
        scenarios = [s for s in scenarios if s.get("domain") == DOMAIN_FILTER]

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
        scenarios_passed = 0

        for scenario in scenarios:
            domain = str(scenario.get("domain") or "unknown")
            sid = f"uat-fu-{scenario['id']}-{uuid.uuid4().hex[:8]}"
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
                judge_block = turn.get("judge") if isinstance(turn.get("judge"), dict) else {}
                min_score = int(judge_block.get("min_score") or 7)
                extra = list(judge_block.get("criteria") or [])
                extra.insert(0, f"Domain: {domain} · scenario {scenario['id']} turn {index + 1}")

                verdict_payload = None
                judge_error = None
                if not SKIP_JUDGE:
                    judge_total += 1
                    verdict, judge_error = await judge_management_turn(
                        question=q,
                        response=body,
                        scenario_title=str(scenario.get("title") or scenario["id"]),
                        turn_index=index + 1,
                        prior_turns=prior_for_judge,
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
                        if mech_ok:
                            turn_ok = True
                            note = f"judge_flake_ok (mechanical pass): {judge_error}"
                        else:
                            turn_ok = False
                            note = f"judge_unavailable: {judge_error}"

                if not turn_ok:
                    scen_ok = False
                if turn_ok:
                    passed += 1

                prior_for_judge.append(
                    {"question": q, "compact_response": compact_chat_response(body)}
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
                jb = f" judge={verdict_payload.get('score')}/10" if verdict_payload else ""
                print(
                    f"{mark} [{domain}] {scenario['id']} t{index + 1}: "
                    f"{body.get('status')} rows={(body.get('data') or {}).get('row_count')} {note}{jb}"
                )

            if scen_ok:
                scenarios_passed += 1
            entry = {
                "id": scenario["id"],
                "domain": domain,
                "title": scenario.get("title"),
                "session_id": sid,
                "pass": scen_ok,
                "turns": turn_results,
            }
            by_domain[domain].append(entry)

        domain_summary = []
        for dom, items in sorted(by_domain.items()):
            d_pass = sum(1 for i in items if i.get("pass"))
            domain_summary.append(
                {"domain": dom, "scenarios_passed": d_pass, "scenarios_total": len(items), "scenarios": items}
            )

        suite_stem = path.stem  # e.g. uat_domain_1x2_followup
        out = BACKEND / "eval" / f"{suite_stem}_run_{uuid.uuid4().hex[:8]}.json"
        payload = {
            "suite": suite_stem,
            "yaml": path.name,
            "base_url": BASE,
            "provider": PROVIDER,
            "judge_enabled": not SKIP_JUDGE,
            "turns_passed": passed,
            "turns_total": total,
            "scenarios_passed": scenarios_passed,
            "scenarios_total": len(scenarios),
            "judge_passed": judge_passed,
            "judge_total": judge_total,
            "by_domain": domain_summary,
        }
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(
            json.dumps(
                {
                    "report": str(out),
                    "scenarios_passed": scenarios_passed,
                    "scenarios_total": len(scenarios),
                    "turns_passed": passed,
                    "turns_total": total,
                    "judge_passed": judge_passed,
                },
                indent=2,
            )
        )
        return 0 if scenarios_passed == len(scenarios) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

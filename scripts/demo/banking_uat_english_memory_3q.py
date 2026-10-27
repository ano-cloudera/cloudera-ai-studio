#!/usr/bin/env python3
"""AMP UAT: English 3-turn memory (total amount → breakdown by channel → highest channel)."""
from __future__ import annotations

import json
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "demo"))

from banking_robustness_10q import http_json, resolve_llm, resolve_model_id, score_turn  # noqa: E402
from banking_robustness_10q import Turn  # noqa: E402

OUT = ROOT / "testing" / "evidence" / "golden-path" / "AMP-READINESS" / "banking-uat-english-memory-3q.json"

TURNS: tuple[Turn, ...] = (
    Turn(
        "uat08_total_amount",
        "What is the total transaction amount?",
        "governed",
        min_rows=1,
        sql_hint="SUM",
    ),
    Turn(
        "uat09_breakdown_channel",
        "Break it down by channel.",
        "follow_up",
        min_rows=2,
        sql_hint="channel",
    ),
    Turn(
        "uat10_highest_channel",
        "Which channel had the highest value?",
        "follow_up",
        min_rows=1,
        sql_hint="channel",
    ),
)


def _extra_checks(turn: Turn, body: dict[str, Any], notes: list[str]) -> None:
    sql = str(body.get("governed_sql") or "").casefold()
    if turn.key == "uat08_total_amount" and sql:
        if "count(distinct customer_id)" in sql.replace(" ", ""):
            notes.append("sql used COUNT(DISTINCT customer_id) instead of SUM(amount)")
        if "sum(amount" not in sql.replace(" ", ""):
            notes.append("sql missing SUM(amount)")
    if turn.key == "uat09_breakdown_channel" and sql:
        if "group by" not in sql:
            notes.append("breakdown missing GROUP BY")
    status = str(body.get("status") or "")
    if turn.key == "uat09_breakdown_channel" and status == "clarification_required":
        notes.append("follow-up asked for metric picker instead of session continuation")


def main() -> int:
    st, _ = http_json("GET", "/health")
    if st != 200:
        print("backend not healthy", file=sys.stderr)
        return 1

    llm_provider, llm_model = resolve_llm()
    model_id, model_name = resolve_model_id()
    session_id = f"uat-en-mem-{uuid.uuid4().hex[:10]}"
    results: list[dict[str, Any]] = []
    passed = 0

    for index, turn in enumerate(TURNS, start=1):
        payload: dict[str, Any] = {
            "session_id": session_id,
            "question": turn.question,
            "provider": llm_provider,
            "model": llm_model,
            "context_sources": [
                {"type": "semantic_model", "id": model_id, "name": model_name},
            ],
        }
        started = time.perf_counter()
        st, body = http_json("POST", "/chat", payload, timeout=300.0)
        elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
        ok, notes = score_turn(turn, body if isinstance(body, dict) else {})
        if isinstance(body, dict):
            _extra_checks(turn, body, notes)
            ok = not notes
        if ok:
            passed += 1
        results.append(
            {
                "index": index,
                "key": turn.key,
                "question": turn.question,
                "http_status": st,
                "ok": ok,
                "notes": notes,
                "elapsed_ms": elapsed_ms,
                "status": body.get("status") if isinstance(body, dict) else None,
                "governed_metric": (body.get("data") or {}).get("governed_metric")
                if isinstance(body, dict)
                else None,
                "governed_sql": (body.get("governed_sql") or "")[:500] if isinstance(body, dict) else None,
            }
        )
        if not ok:
            break

    report = {
        "session_id": session_id,
        "model_id": model_id,
        "passed": passed,
        "total": len(TURNS),
        "ok": passed == len(TURNS),
        "turns": results,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": report["ok"], "passed": passed, "evidence": str(OUT)}, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

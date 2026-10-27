#!/usr/bin/env python3
"""10-turn Ask Data robustness run (governed + follow-ups + guardrails) against live backend."""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

ROOT = Path(__file__).resolve().parents[2]
BASE = os.environ.get("GOLDEN_PATH_API_BASE", "http://127.0.0.1:8001")
OUT = ROOT / "testing" / "evidence" / "golden-path" / "PHASE3-SEMANTIC" / "banking-robustness-10q.json"
MODEL_KEY = os.environ.get("BANKING_SEMANTIC_MODEL_KEY", "banking_analytics")
MODEL_NAME = os.environ.get("BANKING_SEMANTIC_MODEL_NAME", "Banking Analytics")

TurnKind = Literal["governed", "follow_up", "guardrail", "conversational"]


@dataclass(frozen=True)
class Turn:
    key: str
    question: str
    kind: TurnKind
    attach_semantic: bool = True
    expect_status: str = "SUCCESS"
    min_rows: int = 0
    sql_hint: str | None = None


TURNS: tuple[Turn, ...] = (
    Turn("q01_total_customer", "Berapa total customer kita saat ini?", "governed", sql_hint="COUNT"),
    Turn(
        "q02_followup_segment",
        "Bandingkan jumlah customer per tipe akun.",
        "follow_up",
        sql_hint="GROUP BY",
    ),
    Turn(
        "q03_trend_transaksi",
        "Trend jumlah transaksi per bulan (12 bulan terakhir).",
        "governed",
        min_rows=2,
        sql_hint="GROUP BY",
    ),
    Turn(
        "q04_followup_peak_month",
        "Bulan mana yang paling tinggi dari trend tadi?",
        "follow_up",
    ),
    Turn(
        "q05_failed_rate",
        "Berapa failed transaction rate?",
        "governed",
        min_rows=1,
    ),
    Turn(
        "q06_by_channel",
        "Tampilkan total nominal transaksi per channel.",
        "governed",
        min_rows=2,
        sql_hint="channel",
    ),
    Turn(
        "q07_guardrail_python",
        "Bisa bantu keluarkan contoh python code untuk bikin machine learning?",
        "guardrail",
        attach_semantic=False,
        expect_status="UNSUPPORTED",
    ),
    Turn(
        "q08_greeting",
        "Kamu bisa bantu apa aja sih?",
        "conversational",
        attach_semantic=True,
        expect_status="SUCCESS",
        min_rows=0,
    ),
    Turn(
        "q09_top_segments",
        "Top 5 customer segment berdasarkan jumlah transaksi.",
        "governed",
        min_rows=1,
        sql_hint="segment",
    ),
    Turn(
        "q10_followup_priority",
        "Fokus ke segment Priority saja — berapa jumlah transaksinya?",
        "follow_up",
        min_rows=1,
    ),
)


def http_json(method: str, path: str, body: dict | None = None, *, timeout: float = 300.0) -> tuple[int, Any]:
    data = None if body is None else json.dumps(body).encode()
    headers = {"Content-Type": "application/json"} if body is not None else {}
    req = urllib.request.Request(BASE + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode()
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except json.JSONDecodeError:
            return e.code, {"raw": raw}


def resolve_llm() -> tuple[str, str]:
    st, body = http_json("GET", "/models")
    if st != 200:
        raise RuntimeError(f"list LLM models failed: {st} {body}")
    preferred = os.environ.get("ASK_DATA_PROVIDER")
    for item in body.get("models") or []:
        if preferred and item.get("provider") != preferred:
            continue
        if item.get("available") and item.get("id"):
            return str(item["provider"]), str(item["id"])
    for item in body.get("models") or []:
        if item.get("available") and item.get("id"):
            return str(item["provider"]), str(item["id"])
    raise RuntimeError("no available LLM provider — configure Gemini or Qwen in backend .env")


def resolve_model_id() -> tuple[str, str]:
    st, body = http_json("GET", "/api/v1/semantic/models")
    if st != 200:
        raise RuntimeError(f"list models failed: {st} {body}")
    for m in body.get("models") or []:
        if m.get("key") == MODEL_KEY:
            return str(m["id"]), str(m.get("name") or MODEL_NAME)
    if body.get("models"):
        m = body["models"][0]
        return str(m["id"]), str(m.get("name") or MODEL_NAME)
    raise RuntimeError("no semantic models registered")


def score_turn(turn: Turn, body: dict[str, Any]) -> tuple[bool, list[str]]:
    notes: list[str] = []
    status = str(body.get("status") or "")
    if status != turn.expect_status:
        notes.append(f"status={status!r} expected {turn.expect_status!r}")

    if turn.kind == "guardrail":
        return (not notes, notes)

    if turn.expect_status == "SUCCESS" and turn.kind in ("governed", "follow_up"):
        data = body.get("data") or {}
        rows = int(data.get("row_count") or len(data.get("rows") or []))
        if rows < turn.min_rows:
            notes.append(f"row_count={rows} < min {turn.min_rows}")
        sql = str(body.get("governed_sql") or "")
        if turn.kind == "governed" and not sql.strip() and turn.min_rows > 0:
            notes.append("missing governed_sql")
        if turn.sql_hint and sql and turn.sql_hint.casefold() not in sql.casefold():
            notes.append(f"sql missing hint {turn.sql_hint!r}")
        if turn.key == "q09_top_segments" and sql:
            lowered_sql = sql.casefold()
            if "join" not in lowered_sql and "customers" not in lowered_sql:
                notes.append("sql missing customers join for segment breakdown")
            if "segment" not in lowered_sql:
                notes.append("sql missing segment projection")
        if turn.key == "q10_followup_priority" and sql and "priority" not in sql.casefold():
            notes.append("sql missing Priority segment filter")
        if body.get("context_mode") not in ("GOVERNED_SEMANTIC", None) and turn.attach_semantic:
            if body.get("context_mode") != "GOVERNED_SEMANTIC":
                notes.append(f"context_mode={body.get('context_mode')!r}")

    if turn.kind == "conversational":
        answer = str((body.get("answer") or {}).get("direct_answer") or "")
        if len(answer) < 20:
            notes.append("greeting answer too short")
        if "tempo" in answer.casefold() and "q4 2024" in answer.casefold():
            notes.append("greeting still references TEMPO/Q4 demo copy")

    return (not notes, notes)


def main() -> int:
    st, _ = http_json("GET", "/health")
    if st != 200:
        print("backend not healthy at", BASE, file=sys.stderr)
        return 1

    llm_provider, llm_model = resolve_llm()
    model_id, model_name = resolve_model_id()
    session_id = f"robustness-10q-{uuid.uuid4().hex[:10]}"
    results: list[dict[str, Any]] = []
    passed = 0

    for index, turn in enumerate(TURNS, start=1):
        payload: dict[str, Any] = {
            "session_id": session_id,
            "question": turn.question,
            "provider": llm_provider,
            "model": llm_model,
        }
        if turn.attach_semantic:
            payload["context_sources"] = [
                {"type": "semantic_model", "id": model_id, "name": model_name},
            ]
        else:
            payload["context_sources"] = []

        started = time.perf_counter()
        st, body = http_json("POST", "/chat", payload, timeout=300.0)
        elapsed_ms = round((time.perf_counter() - started) * 1000, 1)

        if st != 200:
            ok, notes = False, [f"http_{st}", str(body)[:200]]
            row = {
                "index": index,
                "key": turn.key,
                "kind": turn.kind,
                "question": turn.question,
                "ok": ok,
                "notes": notes,
                "elapsed_ms": elapsed_ms,
            }
            results.append(row)
            print(f"[{index}/10] FAIL {turn.key} — HTTP {st}")
            continue

        ok, notes = score_turn(turn, body if isinstance(body, dict) else {})
        if ok:
            passed += 1
        data = body.get("data") or {} if isinstance(body, dict) else {}
        results.append(
            {
                "index": index,
                "key": turn.key,
                "kind": turn.kind,
                "question": turn.question,
                "ok": ok,
                "notes": notes,
                "elapsed_ms": elapsed_ms,
                "status": body.get("status") if isinstance(body, dict) else None,
                "strategy": body.get("strategy"),
                "context_mode": body.get("context_mode"),
                "presentation_tier": body.get("presentation_tier"),
                "row_count": data.get("row_count"),
                "chart_type": (body.get("chart_spec") or {}).get("type") if isinstance(body, dict) else None,
                "governed_metric": data.get("governed_metric"),
                "direct_answer_preview": str((body.get("answer") or {}).get("direct_answer") or "")[:280]
                if isinstance(body, dict)
                else "",
                "sql_preview": (str(body.get("governed_sql") or "")[:320] if isinstance(body, dict) else ""),
            }
        )
        mark = "OK" if ok else "FAIL"
        print(f"[{index}/10] {mark} {turn.key} ({elapsed_ms}ms) — {notes or 'pass'}")

    report = {
        "session_id": session_id,
        "model_id": model_id,
        "model_key": MODEL_KEY,
        "llm_provider": llm_provider,
        "llm_model": llm_model,
        "api_base": BASE,
        "passed": passed,
        "total": len(TURNS),
        "all_ok": passed == len(TURNS),
        "turns": results,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"report": str(OUT), "passed": passed, "total": len(TURNS)}, indent=2))
    return 0 if report["all_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

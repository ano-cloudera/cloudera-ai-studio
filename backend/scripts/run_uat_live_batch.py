#!/usr/bin/env python3
"""Run live UAT cases from uat_domain_matrix.yaml (one at a time, prints summary)."""
from __future__ import annotations

import asyncio
import json
import sys
import uuid
from pathlib import Path

import httpx
import yaml

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))


BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
PROVIDER = sys.argv[2] if len(sys.argv) > 2 else "gemini"
LIMIT = int(sys.argv[3]) if len(sys.argv) > 3 else 999
TIMEOUT = 300.0


async def main() -> int:
    matrix = yaml.safe_load((BACKEND / "eval" / "uat_domain_matrix.yaml").read_text(encoding="utf-8"))
    cases = [c for c in matrix.get("cases") or [] if c.get("question")][:LIMIT]
    async with httpx.AsyncClient(base_url=BASE.rstrip("/"), timeout=TIMEOUT) as client:
        models = (await client.get("/models")).json()
        model = ""
        for item in models.get("models") or []:
            if item.get("provider") == PROVIDER and item.get("available"):
                model = str(item.get("id") or "")
                break
        if not model:
            print("No model", file=sys.stderr)
            return 1
        results = []
        for case in cases:
            cid = case["id"]
            q = case["question"]
            expect = case.get("expect") or {}
            try:
                r = await client.post(
                    "/chat",
                    json={
                        "session_id": f"uat-{cid}-{uuid.uuid4()}",
                        "question": q,
                        "provider": PROVIDER,
                        "model": model,
                    },
                )
                r.raise_for_status()
                body = r.json()
                status = body.get("status")
                strategy = body.get("strategy")
                rows = (body.get("data") or {}).get("row_count")
                ok = True
                note = ""
                if expect.get("status") and status != expect["status"]:
                    ok = False
                    note = f"want status {expect['status']} got {status}"
                if expect.get("strategy") and strategy != expect["strategy"]:
                    ok = False
                    note = f"want strategy {expect['strategy']} got {strategy}"
                results.append(
                    {
                        "id": cid,
                        "pass": ok,
                        "status": status,
                        "strategy": strategy,
                        "rows": rows,
                        "note": note,
                        "request_id": body.get("request_id"),
                    }
                )
                mark = "OK" if ok else "FAIL"
                print(f"{mark} {cid} {status} {strategy} rows={rows} {note}")
            except Exception as exc:
                results.append({"id": cid, "pass": False, "error": str(exc)})
                print(f"FAIL {cid} {type(exc).__name__}: {exc}")
        passed = sum(1 for r in results if r.get("pass"))
        out = BACKEND / "eval" / "uat_live_batch.json"
        out.write_text(json.dumps({"base": BASE, "passed": passed, "total": len(results), "results": results}, indent=2), encoding="utf-8")
        print(f"\nLive PASS {passed}/{len(results)} -> {out}")
        return 0 if passed == len(results) else 2


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

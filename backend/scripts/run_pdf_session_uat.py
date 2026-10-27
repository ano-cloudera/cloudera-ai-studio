#!/usr/bin/env python3
"""Mechanical UAT for PDF session (uat_pdf_session_oct2026.yaml)."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from pathlib import Path

import httpx
import yaml

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

YAML_PATH = BACKEND / "eval" / "uat_pdf_session_oct2026.yaml"


def _check_resolution(resolution: dict, expect: dict) -> tuple[bool, str]:
    metric = expect.get("metric")
    if metric and resolution.get("metric") != metric:
        return False, f"metric want {metric} got {resolution.get('metric')}"
    if resolution.get("status") not in ("resolved", "needs_clarification"):
        return False, f"resolver status {resolution.get('status')}"
    return True, "ok"


def _check_live(body: dict, expect: dict) -> tuple[bool, str]:
    status = body.get("status")
    strategy = body.get("strategy")
    if expect.get("status") and status != expect["status"]:
        return False, f"status want {expect['status']} got {status}"
    if expect.get("strategy") and strategy != expect["strategy"]:
        return False, f"strategy want {expect['strategy']} got {strategy}"
    rows = int((body.get("data") or {}).get("row_count") or 0)
    min_rows = expect.get("min_rows")
    if min_rows is not None and status == "SUCCESS" and rows < int(min_rows):
        return False, f"row_count {rows} < {min_rows}"
    gm = (body.get("data") or {}).get("governed_metric")
    if expect.get("metric") and gm and gm != expect["metric"]:
        return False, f"governed_metric want {expect['metric']} got {gm}"
    return True, "ok"


async def _live_one(base_url: str, question: str, *, provider: str, model: str, timeout: float) -> dict:
    payload = {
        "session_id": f"pdf-uat-{uuid.uuid4()}",
        "question": question,
        "provider": provider,
        "model": model,
    }
    async with httpx.AsyncClient(base_url=base_url.rstrip("/"), timeout=timeout) as client:
        models = await client.get("/models")
        models.raise_for_status()
        chosen = model
        if not chosen:
            for item in models.json().get("models") or []:
                if item.get("provider") == provider and item.get("available"):
                    chosen = str(item.get("id") or "")
                    break
        payload["model"] = chosen
        response = await client.post("/chat", json=payload)
        response.raise_for_status()
        return response.json()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", metavar="BASE_URL", default="")
    parser.add_argument("provider", nargs="?", default="gemini")
    parser.add_argument("model", nargs="?", default="")
    parser.add_argument("--timeout", type=float, default=240.0)
    args = parser.parse_args()

    from app.core.config import Settings
    from app.semantic.context import SemanticContextService

    data = yaml.safe_load(YAML_PATH.read_text(encoding="utf-8"))
    cases = data.get("cases") or []
    settings = Settings()
    ctx = SemanticContextService(settings.project_root / settings.ossie_project_id)

    dry_rows: list[dict] = []
    passed = 0
    for case in cases:
        q = str(case["question"])
        expect = case.get("expect") or {}
        resolution = ctx.resolve(q)
        ok, msg = _check_resolution(resolution, expect)
        dry_rows.append(
            {
                "id": case["id"],
                "ok": ok,
                "detail": msg,
                "metric": resolution.get("metric"),
                "status": resolution.get("status"),
            }
        )
        if ok:
            passed += 1

    print(f"Dry-run: {passed}/{len(cases)} passed")
    print(json.dumps(dry_rows, ensure_ascii=False, indent=2))

    if not args.live:
        return 0 if passed == len(cases) else 1

    async def run_live() -> list[dict]:
        out: list[dict] = []
        for case in cases:
            expect = case.get("expect") or {}
            try:
                body = await _live_one(
                    args.live,
                    str(case["question"]),
                    provider=args.provider,
                    model=args.model,
                    timeout=args.timeout,
                )
                ok, msg = _check_live(body, expect)
                out.append(
                    {
                        "id": case["id"],
                        "ok": ok,
                        "detail": msg,
                        "status": body.get("status"),
                        "row_count": (body.get("data") or {}).get("row_count"),
                        "governed_metric": (body.get("data") or {}).get("governed_metric"),
                    }
                )
            except Exception as exc:
                out.append({"id": case["id"], "ok": False, "detail": str(exc)})
        return out

    live_rows = asyncio.run(run_live())
    live_pass = sum(1 for r in live_rows if r.get("ok"))
    print(f"\nLive: {live_pass}/{len(cases)} passed")
    print(json.dumps(live_rows, ensure_ascii=False, indent=2))
    return 0 if live_pass == len(cases) else 1


if __name__ == "__main__":
    raise SystemExit(main())

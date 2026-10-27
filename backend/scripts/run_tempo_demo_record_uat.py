#!/usr/bin/env python3
"""Dry-run + optional live UAT for uat_tempo_demo_record_oct2026.yaml."""

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

DEFAULT_YAML = BACKEND / "eval" / "uat_tempo_demo_record_oct2026.yaml"


def _check_resolution(resolution: dict, expect: dict) -> tuple[bool, str]:
    if expect.get("resolve_optional"):
        return True, "ok (analysis follow-up; resolver not required)"
    metric = expect.get("metric")
    if metric:
        allowed = metric if isinstance(metric, list) else [metric]
        if resolution.get("metric") not in allowed:
            return False, f"metric want one of {allowed} got {resolution.get('metric')}"
    st = resolution.get("status")
    if st not in ("resolved", "needs_clarification"):
        return False, f"resolver status {st!r} reason={resolution.get('reason')!r}"
    return True, "ok"


def _check_live(body: dict, expect: dict) -> tuple[bool, str]:
    status = body.get("status")
    strategy = body.get("strategy")
    allowed_status = expect.get("status")
    if allowed_status:
        statuses = allowed_status if isinstance(allowed_status, list) else [allowed_status]
        if status not in statuses:
            return False, f"status want one of {statuses} got {status}"
    allowed_strategy = expect.get("strategy")
    if allowed_strategy:
        strategies = allowed_strategy if isinstance(allowed_strategy, list) else [allowed_strategy]
        if strategy not in strategies:
            return False, f"strategy want one of {strategies} got {strategy}"
    rows = int((body.get("data") or {}).get("row_count") or 0)
    min_rows = expect.get("min_rows")
    if min_rows is not None and status == "SUCCESS" and rows < int(min_rows):
        return False, f"row_count {rows} < {min_rows}"
    gm = (body.get("data") or {}).get("governed_metric")
    metric = expect.get("metric")
    if metric and gm:
        allowed = metric if isinstance(metric, list) else [metric]
        if gm not in allowed:
            return False, f"governed_metric want one of {allowed} got {gm}"
    return True, "ok"


async def _live_chat(
    client: httpx.AsyncClient,
    *,
    session_id: str,
    question: str,
    provider: str,
    model: str,
) -> dict:
    r = await client.post(
        "/chat",
        json={
            "session_id": session_id,
            "question": question,
            "provider": provider,
            "model": model,
        },
    )
    r.raise_for_status()
    return r.json()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--yaml", type=Path, default=DEFAULT_YAML)
    parser.add_argument("--live", metavar="BASE_URL", default="")
    parser.add_argument("provider", nargs="?", default="gemini")
    parser.add_argument("model", nargs="?", default="")
    parser.add_argument("--timeout", type=float, default=360.0)
    parser.add_argument("--batch", type=int, default=0, help="Only run batch 1/2/3 (0=all)")
    parser.add_argument("--skip-scenarios", action="store_true", help="Dry/live management_cases only")
    args = parser.parse_args()

    from app.core.config import Settings
    from app.semantic.context import SemanticContextService

    data = yaml.safe_load(args.yaml.read_text(encoding="utf-8"))
    settings = Settings()
    ctx = SemanticContextService(settings.project_root / settings.ossie_project_id)

    dry_rows: list[dict] = []
    passed = 0
    total = 0

    cases = list(data.get("management_cases") or [])
    if args.batch == 2:
        cases = [c for c in cases if c.get("batch") == 2]
    elif args.batch not in (0, 2):
        cases = []

    for case in cases:
        total += 1
        q = str(case["question"])
        expect = case.get("expect") or {}
        resolution = ctx.resolve(q)
        ok, msg = _check_resolution(resolution, expect)
        dry_rows.append(
            {
                "kind": "case",
                "id": case["id"],
                "ok": ok,
                "detail": msg,
                "metric": resolution.get("metric"),
                "status": resolution.get("status"),
            }
        )
        if ok:
            passed += 1

    if not args.skip_scenarios:
        scenarios = list(data.get("scenarios") or [])
        if args.batch == 1:
            scenarios = [s for s in scenarios if s.get("batch") == 1]
        elif args.batch == 3:
            scenarios = [s for s in scenarios if s.get("batch") == 3]
        elif args.batch == 0:
            pass
        else:
            scenarios = []

        for scenario in scenarios:
            for idx, turn in enumerate(scenario.get("turns") or []):
                total += 1
                q = str(turn["question"])
                expect = turn.get("expect") or {}
                resolution = ctx.resolve(q)
                ok, msg = _check_resolution(resolution, expect)
                dry_rows.append(
                    {
                        "kind": "turn",
                        "id": f"{scenario['id']}#{idx + 1}",
                        "ok": ok,
                        "detail": msg,
                        "metric": resolution.get("metric"),
                        "status": resolution.get("status"),
                    }
                )
                if ok:
                    passed += 1

    print(f"Dry-run: {passed}/{total} passed")
    failed = [r for r in dry_rows if not r.get("ok")]
    if failed:
        print("Failures:", json.dumps(failed, ensure_ascii=False, indent=2))
    if args.live:
        print("(See live summary below; dry-run failures may still fail live.)")
    else:
        print(json.dumps(dry_rows, ensure_ascii=False, indent=2))

    if not args.live:
        return 0 if passed == total else 1

    async def run_live() -> tuple[int, int, list[dict]]:
        out: list[dict] = []
        lp = 0
        lt = 0

        async with httpx.AsyncClient(base_url=args.live.rstrip("/"), timeout=args.timeout) as client:
            health = await client.get("/health")
            health.raise_for_status()
            models = (await client.get("/models")).json()
            model = args.model.strip()
            if not model:
                for item in models.get("models") or []:
                    if item.get("provider") == args.provider and item.get("available"):
                        model = str(item.get("id") or "")
                        break
            if not model:
                raise RuntimeError(f"No model for provider {args.provider}")

            for case in cases:
                lt += 1
                expect = case.get("expect") or {}
                try:
                    body = await _live_chat(
                        client,
                        session_id=f"rec-b2-{case['id']}-{uuid.uuid4().hex[:6]}",
                        question=str(case["question"]),
                        provider=args.provider,
                        model=model,
                    )
                    ok, msg = _check_live(body, expect)
                    if ok:
                        lp += 1
                    out.append(
                        {
                            "kind": "case",
                            "id": case["id"],
                            "ok": ok,
                            "detail": msg,
                            "status": body.get("status"),
                            "strategy": body.get("strategy"),
                            "row_count": (body.get("data") or {}).get("row_count"),
                        }
                    )
                except Exception as exc:
                    out.append({"kind": "case", "id": case["id"], "ok": False, "detail": str(exc)})

            if not args.skip_scenarios:
                scenarios = list(data.get("scenarios") or [])
                if args.batch == 1:
                    scenarios = [s for s in scenarios if s.get("batch") == 1]
                elif args.batch == 3:
                    scenarios = [s for s in scenarios if s.get("batch") == 3]

                for scenario in scenarios:
                    sid = f"rec-{scenario['id']}-{uuid.uuid4().hex[:8]}"
                    for idx, turn in enumerate(scenario.get("turns") or []):
                        lt += 1
                        expect = turn.get("expect") or {}
                        try:
                            body = await _live_chat(
                                client,
                                session_id=sid,
                                question=str(turn["question"]),
                                provider=args.provider,
                                model=model,
                            )
                            ok, msg = _check_live(body, expect)
                            if ok:
                                lp += 1
                            out.append(
                                {
                                    "kind": "turn",
                                    "id": f"{scenario['id']}#{idx + 1}",
                                    "ok": ok,
                                    "detail": msg,
                                    "status": body.get("status"),
                                    "strategy": body.get("strategy"),
                                    "row_count": (body.get("data") or {}).get("row_count"),
                                }
                            )
                        except Exception as exc:
                            out.append(
                                {
                                    "kind": "turn",
                                    "id": f"{scenario['id']}#{idx + 1}",
                                    "ok": False,
                                    "detail": str(exc),
                                }
                            )
        return lp, lt, out

    lp, lt, live_rows = asyncio.run(run_live())
    print(f"\nLive: {lp}/{lt} passed")
    live_failed = [r for r in live_rows if not r.get("ok")]
    if live_failed:
        print("Live failures:", json.dumps(live_failed, ensure_ascii=False, indent=2))
    return 0 if lp == lt else 1


if __name__ == "__main__":
    raise SystemExit(main())

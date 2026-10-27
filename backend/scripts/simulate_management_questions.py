#!/usr/bin/env python3
"""Phase B3 dry-run + optional live Ask Data for management question set."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

MANAGEMENT_QUESTIONS: list[tuple[str, str]] = [
    ("Q01", "Top 10 produk dengan penjualan terbesar di Tempo"),
    ("Q02", "Top 10 cabang/ sales office dengan penjualan terbesar di tempo"),
    (
        "Q03",
        "sekarang bisa bantu tampilkan gak produk/ material 500-21-02 di cabang 0201"
        "dan hitung bisa meng-cover penjualan berapa hari dari stok tersebut",
    ),
    ("Q04", "Top 10 produk di B2B dengan penjualan tertinggi"),
    ("Q05", "Top 10 DC Alfamart dengan penjualan tertinggi"),
    ("Q06", "Cek stok produk A di toko alfamart dan bandingkan dengan stok di DC"),
    ("Q07", "Hitung promo dengan ROI terbaik dan berikan rekomendasi/ saran"),
    ("Q08", "Hitung service level/ fill rate di cabang tempo dan urutkan SL terjelek"),
    (
        "Q09",
        "Analisa data unloading dan picking dan berikan Analisa dan perbandingan dengan Industri standard",
    ),
    ("Q10", "Bantu jelaskan pareto penjualan"),
]


@dataclass
class SimRow:
    qid: str
    question: str
    route: str
    resolution_status: str
    metric: str | None
    reason: str | None


def _dry_run(settings, *, extra_questions: list[tuple[str, str]] | None = None) -> list[SimRow]:
    from app.semantic.context import SemanticContextService
    from app.services.ask_data_routing import resolve_ask_data_route

    ctx = SemanticContextService(settings.project_root / settings.ossie_project_id)
    rows: list[SimRow] = []
    items = list(MANAGEMENT_QUESTIONS)
    if extra_questions:
        items = extra_questions
    for qid, question in items:
        resolution = ctx.resolve(question)
        route = resolve_ask_data_route(question, settings, semantic_resolution=resolution)
        rows.append(
            SimRow(
                qid=qid,
                question=question,
                route=route,
                resolution_status=str(resolution.get("status") or ""),
                metric=resolution.get("metric") if isinstance(resolution.get("metric"), str) else None,
                reason=resolution.get("reason") if isinstance(resolution.get("reason"), str) else None,
            )
        )
    return rows


async def _resolve_model(base_url: str, provider: str, model: str) -> str:
    if model.strip():
        return model.strip()
    import httpx

    async with httpx.AsyncClient(base_url=base_url.rstrip("/"), timeout=30.0) as client:
        response = await client.get("/models")
        response.raise_for_status()
        payload = response.json()
    for item in payload.get("models") or []:
        if item.get("provider") == provider and item.get("available"):
            return str(item.get("id") or "")
    raise RuntimeError(f"No available model for provider={provider}")


async def _live_one(base_url: str, question: str, *, provider: str, model: str, timeout: float) -> dict:
    import httpx

    payload = {
        "session_id": f"phase-b3-{uuid.uuid4()}",
        "question": question,
        "provider": provider,
        "model": model,
    }
    async with httpx.AsyncClient(base_url=base_url.rstrip("/"), timeout=timeout) as client:
        response = await client.post("/chat", json=payload)
        response.raise_for_status()
        return response.json()


async def _live_run(
    base_url: str,
    *,
    provider: str,
    model: str,
    timeout: float,
    limit: int | None,
    ids: set[str] | None,
    extra: list[tuple[str, str]] | None = None,
) -> list[dict]:
    out: list[dict] = []
    items = extra if extra else MANAGEMENT_QUESTIONS
    if not extra and ids:
        items = [(qid, q) for qid, q in items if qid in ids]
    elif not extra and limit is not None:
        items = items[:limit]
    model = await _resolve_model(base_url, provider, model)
    for qid, question in items:
        try:
            body = await _live_one(base_url, question, provider=provider, model=model, timeout=timeout)
            answer = body.get("answer") or {}
            if isinstance(answer, dict):
                summary = (answer.get("executive_summary") or answer.get("direct_answer") or "")[:200]
            else:
                summary = str(answer)[:200]
            out.append(
                {
                    "qid": qid,
                    "status": body.get("status"),
                    "strategy": body.get("strategy"),
                    "row_count": (body.get("data") or {}).get("row_count"),
                    "summary": summary,
                }
            )
        except Exception as exc:
            out.append({"qid": qid, "error": f"{type(exc).__name__}: {exc}"})
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="POST each question to backend /v1/ask-data")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--provider", default="gemini")
    parser.add_argument("--model", default="")
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument("--limit", type=int, default=0, help="Live mode: only first N questions (0 = all)")
    parser.add_argument("--ids", default="", help="Live/dry highlight: comma-separated QIDs e.g. Q01,Q03,Q08")
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--question",
        default="",
        help="Single smoke question (overrides --ids/--limit for live; adds one dry-run row)",
    )
    args = parser.parse_args()

    from app.core.config import Settings

    settings = Settings()
    extra: list[tuple[str, str]] = []
    if args.question.strip():
        extra = [("SMOKE", args.question.strip())]
    rows = _dry_run(settings, extra_questions=extra)

    if args.json:
        print(json.dumps([r.__dict__ for r in rows], ensure_ascii=False, indent=2))
    else:
        mode = (settings.ask_data_routing or "auto").strip().lower()
        print(f"ASK_DATA_ROUTING={mode}  local_agent_primary={settings.local_agent_primary}")
        print(f"LOCAL_AGENT_BASE_URL={settings.local_agent_base_url or '(empty)'}")
        print()
        print(f"{'ID':<4} {'Route':<6} {'Resolver':<22} {'Metric':<28} Question")
        print("-" * 120)
        for r in rows:
            metric = (r.metric or r.reason or "-")[:28]
            q = r.question if len(r.question) <= 48 else r.question[:45] + "..."
            print(f"{r.qid:<4} {r.route:<6} {r.resolution_status:<22} {metric:<28} {q}")

    id_set = {part.strip().upper() for part in args.ids.split(",") if part.strip()}

    if args.live:
        if args.question.strip():
            live = asyncio.run(
                _live_run(
                    args.base_url,
                    provider=args.provider,
                    model=args.model,
                    timeout=args.timeout,
                    limit=None,
                    ids=None,
                    extra=[("SMOKE", args.question.strip())],
                )
            )
        else:
            limit = None if args.limit <= 0 else args.limit
            live = asyncio.run(
                _live_run(
                    args.base_url,
                    provider=args.provider,
                    model=args.model,
                    timeout=args.timeout,
                    limit=limit if not id_set else None,
                    ids=id_set or None,
                    extra=None,
                )
            )
        print("\n--- Live results ---")
        print(json.dumps(live, ensure_ascii=False, indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

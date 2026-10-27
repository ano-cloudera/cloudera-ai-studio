#!/usr/bin/env python3
"""Live 5-question Ask Data run covering presentation tiers 1–3."""
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

from banking_robustness_10q import (  # noqa: E402
    http_json,
    resolve_llm,
    resolve_model_id,
)

OUT = ROOT / "testing" / "evidence" / "golden-path" / "PHASE3-SEMANTIC" / "banking-tier-5q-live.json"

# Designed tier targets (actual tier computed by backend presentation rules).
TIER_5Q = (
    {
        "key": "t1_total_customer",
        "target_tier": 1,
        "label": "Tier 1 — KPI tunggal",
        "question": "Berapa total customer kita saat ini?",
    },
    {
        "key": "t2_by_channel",
        "target_tier": 2,
        "label": "Tier 2 — breakdown dimensi",
        "question": "Tampilkan total nominal transaksi per channel.",
    },
    {
        "key": "t2_customers_by_account",
        "target_tier": 2,
        "label": "Tier 2 — per tipe akun",
        "question": "Bandingkan jumlah customer per tipe akun.",
    },
    {
        "key": "t3_top10_segments",
        "target_tier": 3,
        "label": "Tier 3 — ranking / workspace",
        "question": "Top 10 customer segment berdasarkan total nominal transaksi.",
    },
    {
        "key": "t3_monthly_trend",
        "target_tier": 3,
        "label": "Tier 3 — seri waktu (12 bulan)",
        "question": "Trend jumlah transaksi per bulan (12 bulan terakhir).",
    },
)


def main() -> int:
    st, _ = http_json("GET", "/health")
    if st != 200:
        print("backend not healthy", file=sys.stderr)
        return 1

    provider, model = resolve_llm()
    model_id, model_name = resolve_model_id()
    session_id = f"tier-5q-{uuid.uuid4().hex[:8]}"
    results: list[dict[str, Any]] = []
    tiers_seen: set[int] = set()

    print(f"session={session_id} semantic={model_name} llm={provider}/{model}\n")

    for index, spec in enumerate(TIER_5Q, start=1):
        payload = {
            "session_id": session_id,
            "question": spec["question"],
            "provider": provider,
            "model": model,
            "context_sources": [
                {"type": "semantic_model", "id": model_id, "name": model_name},
            ],
        }
        t0 = time.perf_counter()
        st, body = http_json("POST", "/chat", payload, timeout=360.0)
        elapsed_ms = round((time.perf_counter() - t0) * 1000, 1)
        tier = body.get("presentation_tier")
        try:
            tier_int = int(tier) if tier is not None else None
        except (TypeError, ValueError):
            tier_int = None
        if tier_int is not None:
            tiers_seen.add(tier_int)

        data = body.get("data") or {}
        row_count = int(data.get("row_count") or len(data.get("rows") or []))
        chart = body.get("chart_spec") or {}
        chart_type = chart.get("type") if isinstance(chart, dict) else None
        answer = body.get("answer") or {}
        direct = str(answer.get("direct_answer") or "")[:120]

        ok = st == 200 and str(body.get("status")) == "SUCCESS"
        tier_ok = tier_int == spec["target_tier"] if tier_int is not None else False

        row = {
            "index": index,
            **spec,
            "ok": ok,
            "tier_match": tier_ok,
            "http_status": st,
            "status": body.get("status"),
            "presentation_tier": tier_int,
            "context_mode": body.get("context_mode"),
            "row_count": row_count,
            "chart_type": chart_type,
            "governed_metric": body.get("data", {}).get("governed_metric") or body.get("governed_metric"),
            "direct_answer_preview": direct,
            "elapsed_ms": elapsed_ms,
        }
        results.append(row)

        flag = "✓" if ok and tier_ok else ("~" if ok else "✗")
        print(
            f"{flag} Q{index} [{spec['label']}] tier={tier_int} (target {spec['target_tier']}) "
            f"rows={row_count} chart={chart_type} {elapsed_ms}ms"
        )
        if not tier_ok and ok:
            print(f"    note: tier mismatch (got {tier_int}, wanted {spec['target_tier']})")
        if not ok:
            print(f"    error: http={st} status={body.get('status')} {body.get('detail') or ''}")

    coverage_ok = {1, 2, 3}.issubset(tiers_seen)
    passed = sum(1 for r in results if r["ok"])
    tier_matches = sum(1 for r in results if r.get("tier_match"))

    summary = {
        "session_id": session_id,
        "model_id": model_id,
        "model_name": model_name,
        "llm_provider": provider,
        "llm_model": model,
        "passed": passed,
        "total": len(TIER_5Q),
        "tier_matches": tier_matches,
        "tiers_observed": sorted(tiers_seen),
        "all_three_tiers_observed": coverage_ok,
        "all_ok": passed == len(TIER_5Q),
        "turns": results,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"\nSummary: {passed}/{len(TIER_5Q)} SUCCESS, tier hits {tier_matches}/{len(TIER_5Q)}, "
          f"tiers seen {sorted(tiers_seen)}, coverage 1+2+3={coverage_ok}")
    print(f"Evidence: {OUT.relative_to(ROOT)}")
    return 0 if passed == len(TIER_5Q) and coverage_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

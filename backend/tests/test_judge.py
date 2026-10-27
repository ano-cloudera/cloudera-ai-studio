from __future__ import annotations

from app.graph.inquiry_brief import build_inquiry_brief
from app.graph.judge import deterministic_judge, judge_review


def test_inquiry_brief_detects_rank_and_analysis() -> None:
    brief = build_inquiry_brief(
        "Tampilkan 10 DC dengan stok tertinggi, lalu analisa perbaikannya",
        semantic_resolution={"status": "resolved", "metric": "material_warehouse_stock_quantity"},
        query_plan={"strategy": "governed", "metrics": ["material_warehouse_stock_quantity"], "analysis_type": "ranking"},
    )
    assert brief["wants_rank"] is True
    assert brief["wants_operational_analysis"] is True
    assert brief["expected_metric"] == "material_warehouse_stock_quantity"


def test_judge_flags_missing_operational_analysis() -> None:
    state = {
        "inquiry_brief": {"wants_operational_analysis": True},
        "answer": {"direct_answer": "OK", "insights": [], "business_implications": [], "data_reference": "gold.foo"},
        "query_plan": {"metrics": ["m1"]},
        "validated_sql": "SELECT 1 FROM gold.foo ORDER BY x LIMIT 10",
        "query_result": {"row_count": 2},
        "status": "SUCCESS",
        "strategy": "governed",
    }
    issues = deterministic_judge(state)
    assert any("Operational analysis" in i for i in issues)
    review = judge_review({**state, "judge_iteration": 0}, max_iterations=2)
    assert review["accept"] is False
    assert review["retry_decision"] == "retry_synthesize"


def test_judge_measure_mismatch_requests_replan() -> None:
    state = {
        "inquiry_brief": {"expected_metric": "sat_dc_stock_quantity", "wants_rank": True, "rank_limit": 10},
        "answer": {"direct_answer": "OK", "insights": [], "business_implications": [], "data_reference": "gold.foo"},
        "query_plan": {"metrics": ["other_metric"]},
        "validated_sql": "SELECT 1 FROM gold.foo",
        "query_result": {"row_count": 1},
        "status": "SUCCESS",
        "strategy": "governed",
    }
    review = judge_review({**state, "judge_iteration": 0}, max_iterations=2)
    assert review["retry_decision"] == "retry_plan"

from app.graph.judge import judge_fast_path_accept, judge_review


def test_judge_fast_path_accepts_simple_governed_success() -> None:
    state = {
        "strategy": "governed",
        "status": "SUCCESS",
        "inquiry_brief": {"wants_rank": True, "rank_limit": 10},
        "semantic_resolution": {"status": "resolved", "metric": "b2b_branch_sell_out_value"},
        "validated_sql": "SELECT d.branch, SUM(x) AS metric_value FROM t d GROUP BY d.branch ORDER BY metric_value DESC LIMIT 10",
        "query_result": {"row_count": 10},
        "answer": {"direct_answer": "DC A leads."},
    }
    assert judge_fast_path_accept(state) is True
    review = judge_review(state, max_iterations=2)
    assert review["accept"] is True


def test_judge_fast_path_rejects_operational_analysis() -> None:
    state = {
        "strategy": "governed",
        "status": "SUCCESS",
        "inquiry_brief": {"wants_operational_analysis": True},
        "semantic_resolution": {"status": "resolved"},
        "query_result": {"row_count": 5},
        "answer": {"direct_answer": "x"},
    }
    assert judge_fast_path_accept(state) is False

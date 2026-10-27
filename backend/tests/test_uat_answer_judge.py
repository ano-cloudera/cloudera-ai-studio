from eval.uat_answer_judge import compact_chat_response, _default_criteria


def test_compact_chat_response_truncates_rows() -> None:
    body = {
        "status": "SUCCESS",
        "strategy": "governed",
        "data": {
            "row_count": 10,
            "columns": ["branch", "metric_value"],
            "rows": [{"branch": f"DC {i}", "metric_value": i} for i in range(10)],
        },
        "answer": {"direct_answer": "Top DC listed.", "caveats": []},
    }
    compact = compact_chat_response(body, max_rows=3)
    assert len(compact["sample_rows"]) == 3
    assert compact["row_count"] == 10


def test_default_criteria_clarification() -> None:
    lines = _default_criteria("CLARIFICATION", "clarification")
    assert any("CLARIFICATION" in line for line in lines)

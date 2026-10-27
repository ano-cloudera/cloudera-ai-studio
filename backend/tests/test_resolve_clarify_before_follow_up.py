from app.services.follow_up import build_analysis_context
from app.semantic.context import SemanticContextService


def test_clarification_wins_over_follow_up_context() -> None:
    ctx = build_analysis_context(
        metric="b2b_branch_sell_out_value",
        dimensions=["branch"],
        entity_dimension="branch",
        ranked_entities=[{"rank": 1, "dimension": "branch", "id": "DC Palembang"}],
        last_question="top dc",
    )
    q = (
        "Analisa data unloading dan picking dan berikan analisa perbandingan "
        "dengan industri standard"
    )
    resolution = SemanticContextService().resolve(q, session_analysis_context=ctx)
    assert resolution.get("status") == "needs_clarification"
    assert resolution.get("reason") == "warehouse_ops_dual_metric"

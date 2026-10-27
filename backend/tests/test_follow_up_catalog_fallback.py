from app.graph.workflow import _row_from_follow_up_catalog
from app.services.follow_up import build_analysis_context, try_follow_up_governed_resolution


def test_follow_up_resolution_includes_catalog_entity() -> None:
    ctx = build_analysis_context(
        metric="b2b_branch_sell_out_value",
        dimensions=["branch"],
        entity_dimension="branch",
        ranked_entities=[
            {"rank": 1, "dimension": "branch", "id": "DC Palembang", "metric_value": 123.0},
        ],
        last_question="top cabang",
    )
    q = "untuk cabang rank 1 dari hasil itu, sebutkan nilai sell-out dan nama DC-nya"
    res = try_follow_up_governed_resolution(q, ctx, understanding=None)
    assert res is not None
    assert res.get("follow_up_catalog_entity", {}).get("id") == "DC Palembang"


def test_synthetic_catalog_row_shape() -> None:
    row = _row_from_follow_up_catalog(
        {"dimension": "branch", "id": "DC Palembang", "metric_value": 99.5}
    )
    assert row == {"branch": "DC Palembang", "metric_value": 99.5}

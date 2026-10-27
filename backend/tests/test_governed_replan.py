from app.graph.governed_replan import rank_dimensions_for_brief


def test_rank_dc_grain_prefers_dcname() -> None:
    brief = {
        "wants_rank": True,
        "wants_dc_grain": True,
        "wants_product_grain": False,
        "rank_limit": 10,
    }
    assert rank_dimensions_for_brief(brief, {"dcname", "plu"}) == ["dcname"]

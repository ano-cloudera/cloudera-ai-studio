from app.services.follow_up import build_analysis_context, plan_follow_up, try_follow_up_governed_resolution


def test_rank_one_b2b_branch_filter_without_llm_understanding() -> None:
    ctx = build_analysis_context(
        metric="b2b_branch_sell_out_value",
        dimensions=["branch"],
        entity_dimension="branch",
        ranked_entities=[
            {"rank": 1, "dimension": "branch", "id": "DC Palembang", "metric_value": 1e10},
            {"rank": 2, "dimension": "branch", "id": "DC Makassar", "metric_value": 9e9},
        ],
        last_question="top penjualan cabang Alfamart?",
    )
    q = "untuk cabang rank 1 dari hasil itu, sebutkan nilai sell-out dan nama DC-nya"
    res = try_follow_up_governed_resolution(q, ctx, understanding=None)
    assert res is not None
    assert res["metric"] == "b2b_branch_sell_out_value"
    assert any("DC Palembang" in p for p in res.get("follow_up_entity_filters") or [])


def test_compare_urutan_one_and_two() -> None:
    ctx = build_analysis_context(
        metric="b2b_branch_sell_out_value",
        dimensions=["branch"],
        entity_dimension="branch",
        ranked_entities=[
            {"rank": 1, "dimension": "branch", "id": "DC A", "metric_value": 1},
            {"rank": 2, "dimension": "branch", "id": "DC B", "metric_value": 2},
        ],
        last_question="top cabang",
    )
    q = "dari ranking itu, bandingkan DC urutan 1 dan urutan 2"
    plan = plan_follow_up(q, ctx)
    assert plan is not None
    assert plan.intent == "compare"
    res = try_follow_up_governed_resolution(q, ctx, understanding=None)
    assert res is not None
    preds = " ".join(res.get("follow_up_entity_filters") or [])
    assert "DC A" in preds and "DC B" in preds


def test_fe001_material_follow_up_after_company_total() -> None:
    ctx = build_analysis_context(
        metric="material_warehouse_stock_quantity",
        dimensions=["calmonth"],
        entity_dimension=None,
        ranked_entities=[],
        last_question="total stok gudang Tempo company-wide Q4 2024",
    )
    q = "bagaimana stok material FE001 dibanding total tadi?"
    res = try_follow_up_governed_resolution(q, ctx, understanding=None)
    assert res is not None
    assert "FE001" in " ".join(res.get("follow_up_entity_filters") or [])


def test_sales_office_unloading_monthly_for_worst_office() -> None:
    ctx = build_analysis_context(
        metric="average_unloading_minutes",
        dimensions=["sales_off"],
        entity_dimension="sales_off",
        ranked_entities=[
            {"rank": 1, "dimension": "sales_off", "id": "SO-JKT", "metric_value": 45.0},
        ],
        last_question="sales office dengan unloading terlama Q4",
    )
    q = "office itu tampilkan rata-rata unloading per bulan"
    res = try_follow_up_governed_resolution(q, ctx, understanding=None)
    assert res is not None
    assert res["metric"] == "average_unloading_minutes"
    assert res["dimensions"] == ["reporting_period"]
    assert any("SO-JKT" in p for p in res.get("follow_up_entity_filters") or [])


def test_relimit_top_five_from_prior_ranking() -> None:
    ctx = build_analysis_context(
        metric="b2b_branch_sell_out_value",
        dimensions=["branch"],
        entity_dimension="branch",
        ranked_entities=[{"rank": i, "dimension": "branch", "id": f"DC {i}"} for i in range(1, 11)],
        last_question="sell-out per cabang",
    )
    q = "tampilkan hanya top 5 saja dari daftar tadi"
    res = try_follow_up_governed_resolution(q, ctx, understanding=None)
    assert res is not None
    assert res["metric"] == "b2b_branch_sell_out_value"

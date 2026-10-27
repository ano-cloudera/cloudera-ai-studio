from app.services.follow_up import (
    build_analysis_context,
    plan_follow_up,
    try_follow_up_governed_resolution,
    try_history_only_analysis_resolution,
)


def test_unloading_compare_follow_up_from_prior_office_codes() -> None:
    ctx = build_analysis_context(
        metric="average_unloading_minutes",
        dimensions=["sales_office"],
        entity_dimension="sales_office",
        ranked_entities=[],
        last_question="Bandingkan rata-rata unloading sales office 0201 vs 0202 Q4 2024",
    )
    q = "office mana yang lebih lambat dan selisihnya berapa menit?"
    plan = plan_follow_up(q, ctx)
    assert plan is not None
    assert plan.intent == "compare"
    assert plan.compare_entities is not None
    ids = {str(e["id"]) for e in plan.compare_entities}
    assert ids == {"0201", "0202"}


def test_service_level_worst_office_material_drill() -> None:
    ctx = build_analysis_context(
        metric="sales_office_service_fill_rate",
        dimensions=["sales_off"],
        entity_dimension="sales_off",
        ranked_entities=[{"rank": 1, "dimension": "sales_off", "id": "0245", "metric_value": 0.4}],
        last_question="Hitung service level cabang tempo urutkan SL terjelek Q4",
    )
    q = "cabang paling jelek tadi, top 5 material dengan fill rate terendah"
    res = try_follow_up_governed_resolution(q, ctx, understanding=None)
    assert res is not None
    assert res["metric"] == "sales_office_service_fill_rate"
    assert "material" in res["dimensions"]


def test_sales_office_compare_from_question_office_codes() -> None:
    ctx = build_analysis_context(
        metric="sales_office_material_sell_in_value",
        dimensions=["sales_office", "material"],
        entity_dimension="sales_office",
        ranked_entities=[{"rank": 1, "id": "0201", "dimension": "sales_office"}],
        last_question="Top 5 material sell-in office 0201 Q4 2024",
    )
    q = "bandingkan total sell-in office 0201 vs 0280 Q4 untuk konteks yang sama"
    res = try_follow_up_governed_resolution(q, ctx, understanding=None)
    assert res is not None
    assert res["metric"] == "sales_office_sell_in_value"
    assert "sales_office" in res["dimensions"]
    filters = " ".join(res.get("follow_up_entity_filters") or [])
    assert "0201" in filters and "0280" in filters


def test_sales_office_compare_ignores_unrelated_prior_metric() -> None:
    """After SAT/DC turns, office penjualan compare must not reuse sat_dc_stock_quantity."""
    ctx = build_analysis_context(
        metric="sat_dc_stock_quantity",
        dimensions=["dcname"],
        entity_dimension="dcname",
        ranked_entities=[{"rank": 1, "id": "DC Palembang", "dimension": "dcname"}],
        last_question="DC SAT mana stoknya paling tinggi Q4 2024?",
    )
    q = "Bandingkan total penjualan sales office 0201 vs 0280 Q4 2024"
    res = try_follow_up_governed_resolution(q, ctx, understanding=None)
    assert res is not None
    assert res["metric"] == "sales_office_sell_in_value"
    filters = " ".join(res.get("follow_up_entity_filters") or [])
    assert "0201" in filters and "0280" in filters


def test_pareto_top3_contribution_relimit() -> None:
    ctx = build_analysis_context(
        metric="material_sell_in_value",
        dimensions=["material"],
        entity_dimension="material",
        ranked_entities=[
            {"rank": 1, "id": "A", "dimension": "material"},
            {"rank": 2, "id": "B", "dimension": "material"},
            {"rank": 3, "id": "C", "dimension": "material"},
        ],
        last_question="pareto sell-in top produk",
    )
    plan = plan_follow_up("tiga produk teratas tadi, berapa persen kontribusi ke total sell-in?", ctx)
    assert plan is not None
    assert plan.intent == "relimit"
    assert plan.limit == 3


def test_stock_sat_dc_palembang_makassar_compare_follow_up() -> None:
    ctx = build_analysis_context(
        metric="sat_dc_stock_quantity",
        dimensions=["dcname"],
        entity_dimension="dcname",
        ranked_entities=[],
        last_question="Berapa stok SAT di DC Palembang Q4 2024?",
    )
    q = "bandingkan dengan DC Makassar untuk periode yang sama"
    res = try_follow_up_governed_resolution(q, ctx, understanding=None)
    assert res is not None
    assert res["metric"] == "sat_dc_stock_quantity"
    assert "dcname" in res["dimensions"]
    filters = " ".join(res.get("follow_up_entity_filters") or [])
    assert "PALEMBANG" in filters.upper() and "MAKASSAR" in filters.upper()


def test_service_level_low_fill_band_offices_follow_up() -> None:
    ctx = build_analysis_context(
        metric="service_fill_rate",
        dimensions=["fill_rate_band"],
        entity_dimension="fill_rate_band",
        ranked_entities=[],
        last_question="Distribusi fill rate band service level Q4 2024",
    )
    q = "band terendah, list sales office yang dominan di band itu"
    res = try_follow_up_governed_resolution(q, ctx, understanding=None)
    assert res is not None
    assert res["metric"] == "sales_office_service_fill_rate"
    assert "sales_off" in res["dimensions"]
    assert any("low_fill" in p for p in res.get("follow_up_entity_filters") or [])


def test_service_level_po_do_gap_office_material_drill() -> None:
    ctx = build_analysis_context(
        metric="sales_office_service_unfulfilled_quantity",
        dimensions=["sales_off"],
        entity_dimension="sales_off",
        ranked_entities=[{"rank": 1, "id": "0245", "dimension": "sales_off", "metric_value": 9000}],
        last_question="Sales office mana dengan gap PO vs DO terbesar Q4 2024?",
    )
    q = "office dengan gap terbesar tadi, breakdown per material top 5"
    res = try_follow_up_governed_resolution(q, ctx, understanding=None)
    assert res is not None
    assert res["metric"] == "sales_office_service_unfulfilled_quantity"
    assert res["dimensions"] == ["material"]
    assert any("0245" in p for p in res.get("follow_up_entity_filters") or [])


def test_stock_tempo_rank1_sell_in_crosscheck_uses_sell_in_metric() -> None:
    ctx = build_analysis_context(
        metric="material_warehouse_stock_quantity",
        dimensions=["material"],
        entity_dimension="material",
        ranked_entities=[{"rank": 1, "id": "RM00001881", "dimension": "material", "metric_value": -1025045}],
        last_question="Material mana yang stok gudang Tempo-nya paling rendah Q4? Top 10",
    )
    q = "material rank 1 yang stok rendah itu, apakah sell-in Q4-nya juga rendah?"
    res = try_follow_up_governed_resolution(q, ctx, understanding=None)
    assert res is not None
    assert res["metric"] == "material_sell_in_value"
    assert any("RM00001881" in p for p in res.get("follow_up_entity_filters") or [])


def test_stock_tempo_plant_top_materials_follow_up() -> None:
    ctx = build_analysis_context(
        metric="stock_tempo_total_qty",
        dimensions=["plant"],
        entity_dimension="plant",
        ranked_entities=[{"rank": 1, "id": "2300", "dimension": "plant", "metric_value": 1e6}],
        last_question="Plant mana dengan total stok Tempo tertinggi Q4 2024?",
    )
    q = "plant teratas tadi, top 5 material by stock"
    res = try_follow_up_governed_resolution(q, ctx, understanding=None)
    assert res is not None
    assert res["metric"] == "stock_tempo_total_qty"
    assert "material" in res["dimensions"]
    assert any("2300" in p for p in res.get("follow_up_entity_filters") or [])


def test_picking_slowest_vs_fastest_from_same_ranking_compare() -> None:
    ctx = build_analysis_context(
        metric="average_picking_minutes",
        dimensions=["sales_office"],
        entity_dimension="sales_office",
        ranked_entities=[
            {"rank": 1, "id": "0234", "dimension": "sales_office", "metric_value": 23.5},
            {"rank": 10, "id": "0274", "dimension": "sales_office", "metric_value": 12.1},
        ],
        last_question="Sales office mana dengan rata-rata durasi picking terlama Q4 2024?",
    )
    q = "office terlama tadi, bandingkan dengan office tercepat dari ranking yang sama"
    plan = plan_follow_up(q, ctx)
    assert plan is not None
    assert plan.intent == "compare"
    assert plan.compare_entities is not None
    ids = {str(e["id"]) for e in plan.compare_entities}
    assert ids == {"0234", "0274"}


def test_picking_fastest_vs_office_0201_compare_follow_up() -> None:
    ctx = build_analysis_context(
        metric="average_picking_minutes",
        dimensions=["sales_office"],
        entity_dimension="sales_office",
        ranked_entities=[{"rank": 1, "id": "0274", "dimension": "sales_office", "metric_value": 12.5}],
        last_question="Sales office mana picking-nya paling efisien (tercepat) Q4 2024?",
    )
    q = "bandingkan durasi picking office tercepat vs office 0201"
    res = try_follow_up_governed_resolution(q, ctx, understanding=None)
    assert res is not None
    assert res["metric"] == "average_picking_minutes"
    filters = " ".join(res.get("follow_up_entity_filters") or [])
    assert "0274" in filters and "0201" in filters


def test_unloading_company_avg_follow_up_aggregate() -> None:
    ctx = build_analysis_context(
        metric="average_unloading_minutes",
        dimensions=["sales_office"],
        entity_dimension="sales_office",
        ranked_entities=[{"rank": 1, "id": "0201", "dimension": "sales_office", "metric_value": 90.0}],
        last_question="Sales office mana unloading-nya paling efisien (tercepat) Q4 2024?",
    )
    q = "rata-rata unloading company-wide Q4?"
    plan = plan_follow_up(q, ctx)
    assert plan is not None
    assert plan.intent == "aggregate"


def test_stock_sat_dc_rank1_plu_drill_follow_up() -> None:
    ctx = build_analysis_context(
        metric="sat_dc_stock_quantity",
        dimensions=["dcname"],
        entity_dimension="dcname",
        ranked_entities=[{"rank": 1, "id": "DC MAKASSAR", "dimension": "dcname", "metric_value": 500_000}],
        last_question="Top 10 DC dengan penumpukan stok SAT tertinggi Q4 2024",
    )
    q = "DC rank 1 tadi, top 5 PLU dengan stok retail tertinggi"
    res = try_follow_up_governed_resolution(q, ctx, understanding=None)
    assert res is not None
    assert res["metric"] == "sat_store_stock_quantity"
    assert "plu" in res["dimensions"]
    filters = " ".join(res.get("follow_up_entity_filters") or [])
    assert "MAKASSAR" in filters.upper()


def test_stock_sat_division_to_dc_support_follow_up() -> None:
    ctx = build_analysis_context(
        metric="sat_store_stock_quantity",
        dimensions=["division"],
        entity_dimension="division",
        ranked_entities=[{"rank": 1, "id": "FOOD", "dimension": "division", "metric_value": 1_000_000}],
        last_question="Berapa stok retail SAT per division Q4 2024? Top 10 division",
    )
    q = "division teratas, DC mana yang menopang stok terbesar?"
    res = try_follow_up_governed_resolution(q, ctx, understanding=None)
    assert res is not None
    assert res["metric"] == "sat_dc_stock_quantity"
    assert "dcname" in res["dimensions"]
    filters = " ".join(res.get("follow_up_entity_filters") or [])
    assert "FOOD" in filters.upper()
    assert "MANA" not in filters.upper()


def test_sell_in_top_material_b2b_sameness_follow_up() -> None:
    ctx = build_analysis_context(
        metric="material_sell_in_value",
        dimensions=["material"],
        entity_dimension="material",
        ranked_entities=[
            {"rank": 1, "id": "001-00-03", "dimension": "material", "metric_value": 289_450_000_000},
            {"rank": 2, "id": "073-09-03", "dimension": "material", "metric_value": 181_320_000_000},
        ],
        last_question="Top produk sell-in Q4 2024 berdasarkan nilai billing",
    )
    q = (
        "kenapa produk/material itu bisa lebih tinggi, dan apakah bisa di cek juga di penjualan B2b "
        "apakah penjualannya sama atau tidak ?"
    )
    res = try_follow_up_governed_resolution(q, ctx, understanding=None)
    assert res is not None
    assert res["metric"] == "material_sell_out_to_sell_in_value_ratio"
    assert res["dimensions"] == ["material"]
    filters = " ".join(res.get("follow_up_entity_filters") or [])
    assert "001-00-03" in filters


def test_cross_domain_dc_sell_out_product_drill_follow_up() -> None:
    ctx = build_analysis_context(
        metric="sat_dc_stock_quantity",
        dimensions=["dcname"],
        entity_dimension="dcname",
        ranked_entities=[{"rank": 1, "id": "DC Makassar", "dimension": "dcname", "metric_value": 500_000}],
        last_question="DC Alfamart mana stok SAT-nya paling tinggi Q4?",
    )
    q = "DC yang muncul di jawaban tadi, top 3 produk sell-out-nya"
    res = try_follow_up_governed_resolution(q, ctx, understanding=None)
    assert res is not None
    assert res["metric"] == "b2b_branch_material_sell_out_value"
    assert "material" in res["dimensions"]
    filters = " ".join(res.get("follow_up_entity_filters") or [])
    assert "MAKASSAR" in filters.upper()


def test_stock_tempo_fe001_follow_up_metric() -> None:
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
    assert res["metric"] == "material_warehouse_stock_quantity"
    assert any("FE001" in p for p in res.get("follow_up_entity_filters") or [])


def test_promo_status_dominant_to_uplift_material_follow_up() -> None:
    ctx = build_analysis_context(
        metric="promo_observation_count",
        dimensions=["program_status"],
        entity_dimension="program_status",
        ranked_entities=[
            {"rank": 1, "id": "Y", "dimension": "program_status", "metric_value": 1200},
            {"rank": 2, "id": "X", "dimension": "program_status", "metric_value": 400},
        ],
        last_question="Distribusi promo SAT by program status Q4 2024",
    )
    q = "status dominan tadi, top 5 material by uplift"
    res = try_follow_up_governed_resolution(q, ctx, understanding=None)
    assert res is not None
    assert res["metric"] == "promo_material_revenue_uplift"
    assert "material" in res["dimensions"]
    filters = " ".join(res.get("follow_up_entity_filters") or [])
    assert "program_status" in filters.casefold()
    assert "'Y'" in filters or "Y" in filters


def test_service_level_worst_office_unfulfilled_material_drill() -> None:
    ctx = build_analysis_context(
        metric="sales_office_service_fill_rate",
        dimensions=["sales_off"],
        entity_dimension="sales_off",
        ranked_entities=[{"rank": 1, "id": "0245", "dimension": "sales_off", "metric_value": 0.42}],
        last_question="10 sales office dengan fill rate terendah Q4 2024",
    )
    q = "cabang paling jelek dari ranking tadi, 5 material dengan unfulfilled quantity terbesar"
    res = try_follow_up_governed_resolution(q, ctx, understanding=None)
    assert res is not None
    assert res["metric"] == "sales_office_service_unfulfilled_quantity"
    assert res["dimensions"] == ["material"]
    filters = " ".join(res.get("follow_up_entity_filters") or [])
    assert "0245" in filters


def test_explicit_top10_material_not_follow_up_filter_after_pareto() -> None:
    ctx = build_analysis_context(
        metric="material_sell_in_value",
        dimensions=["material"],
        entity_dimension="material",
        ranked_entities=[{"rank": 1, "id": "FE001", "dimension": "material", "metric_value": 1e6}],
        last_question="Tampilkan pareto penjualan",
    )
    q = "Top 10 material dengan nilai sell-in tertinggi Q4 2024"
    assert plan_follow_up(q, ctx) is None


def test_dibanding_does_not_force_fresh_query_for_why_explain() -> None:
    from app.services.follow_up import _follow_up_requires_fresh_query, plan_follow_up

    ctx = build_analysis_context(
        metric="material_sell_in_value",
        dimensions=["material"],
        entity_dimension="material",
        ranked_entities=[{"rank": 1, "id": "A", "dimension": "material"}],
        last_question="Top 10 material sell-in Q4 2024",
    )
    q = "Kenapa material urutan 1 bisa paling tinggi dibanding yang lain?"
    assert _follow_up_requires_fresh_query(q) is False
    plan = plan_follow_up(q, ctx)
    assert plan is not None and plan.intent == "explain_prior_result"


def test_explain_rank_one_vs_peers_uses_history_not_governed_filter() -> None:
    ctx = build_analysis_context(
        metric="material_sell_in_value",
        dimensions=["material"],
        entity_dimension="material",
        ranked_entities=[
            {"rank": 1, "id": "001-00-03", "dimension": "material", "metric_value": 9_500_000},
            {"rank": 2, "id": "002-00-01", "dimension": "material", "metric_value": 7_100_000},
        ],
        last_question="Top 10 material sell-in Tempo Q4 2024",
    )
    q = "Kenapa material urutan 1 bisa paling tinggi dibanding yang lain?"
    plan = plan_follow_up(q, ctx)
    assert plan is not None
    assert plan.intent == "explain_prior_result"
    assert try_follow_up_governed_resolution(q, ctx, understanding=None) is None

    history = [
        {
            "question": ctx["last_question"],
            "answer": {"direct_answer": "Material 001-00-03 memimpin ranking sell-in.", "data_reference": "v_material_sell_in"},
            "rows": [
                {"material": "001-00-03", "metric_value": 9_500_000},
                {"material": "002-00-01", "metric_value": 7_100_000},
            ],
            "strategy": "governed",
            "status": "SUCCESS",
            "session_frame": {"last_metric": "material_sell_in_value", "last_dimensions": ["material"]},
        }
    ]
    hist = try_history_only_analysis_resolution(q, ctx, history, understanding=None)
    assert hist is not None
    assert hist["status"] == "history_only"
    assert hist["prior_query_result"]["row_count"] == 2
    assert hist["focus_entity"]["id"] == "001-00-03"

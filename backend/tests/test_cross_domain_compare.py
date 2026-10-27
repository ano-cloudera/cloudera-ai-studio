from app.services.cross_domain_compare import detect_concepts, try_resolve_cross_domain
from app.services.follow_up import build_analysis_context, try_follow_up_governed_resolution


def test_detects_sell_in_and_b2b_concepts() -> None:
    concepts = detect_concepts("bandingkan sell-in Tempo vs penjualan B2B Alfamart Q4")
    assert "sell_in" in concepts
    assert concepts & {"b2b", "sell_out"}


def test_single_turn_aggregate_sell_in_vs_sell_out() -> None:
    res = try_resolve_cross_domain(
        "Big picture lintas domain: selisih nilai sell-in Tempo vs sell-out partner Q4 2024"
    )
    assert res is not None
    assert res.metric == "sell_out_to_sell_in_value_ratio"
    assert res.dimensions == []


def test_single_turn_material_journey_ratio() -> None:
    res = try_resolve_cross_domain(
        "Untuk material 001-00-03 bandingkan sell-in dan sell-out B2B apakah selaras?"
    )
    assert res is not None
    assert res.metric == "material_sell_out_to_sell_in_value_ratio"
    assert res.dimensions == ["material"]


def test_single_turn_stock_tempo_vs_sell_in() -> None:
    res = try_resolve_cross_domain("Bandingkan stok gudang Tempo vs sell-in per material Q4")
    assert res is not None
    assert res.metric == "stock_tempo_to_sell_in_ratio"
    assert "material" in res.dimensions


def test_single_turn_dc_stock_vs_sell_out() -> None:
    res = try_resolve_cross_domain(
        "Journey: DC dengan stok SAT tinggi sekaligus sell-out partner lemah — ranking cabang Q4"
    )
    assert res is not None
    assert res.metric == "branch_sell_out_vs_dc_stock"
    assert res.dimensions == ["branch"]


def test_follow_up_sell_in_material_to_b2b_check() -> None:
    ctx = build_analysis_context(
        metric="material_sell_in_value",
        dimensions=["material"],
        entity_dimension="material",
        ranked_entities=[{"rank": 1, "id": "001-00-03", "dimension": "material", "metric_value": 1.0}],
        last_question="Top produk sell-in Q4",
    )
    q = "material itu — cek juga penjualan B2B apakah sama?"
    res = try_follow_up_governed_resolution(q, ctx, understanding=None)
    assert res is not None
    assert res["metric"] == "material_sell_out_to_sell_in_value_ratio"


def test_stock_tempo_vs_sell_in_wins_over_service_session_follow_up() -> None:
    from app.semantic.context import SemanticContextService

    ctx = build_analysis_context(
        metric="sales_office_service_fill_rate",
        dimensions=["sales_off"],
        entity_dimension="sales_off",
        ranked_entities=[{"rank": 1, "id": "0201", "dimension": "sales_off", "metric_value": 0.5}],
        last_question="Sales office mana dengan fill rate terendah Q4 2024? Top 10",
    )
    svc = SemanticContextService()
    for q in (
        "Bandingkan stok gudang Tempo vs sell-in per material Q4 2024",
        "Bandingkan stok gudang Tempo vs penjualan di tempo per material Q4 2024",
    ):
        res = svc.resolve(q, session_analysis_context=ctx)
        assert res.get("metric") == "stock_tempo_to_sell_in_ratio", q
        assert res.get("matched_alias") == "cross_domain_stock_tempo_sell_in"

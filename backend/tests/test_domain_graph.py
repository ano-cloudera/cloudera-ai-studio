from app.graph.inquiry_brief import build_inquiry_brief
from app.semantic.context import SemanticContextService
from app.semantic.domain_graph import (
    build_business_context,
    classify_cabang_grain,
    detect_domain_ids,
    journey_for_domains,
    load_domain_graph,
    try_clarification_intent,
    try_governed_intent_route,
)


def test_domain_graph_loads() -> None:
    graph = load_domain_graph()
    assert graph.get("version") == 1
    assert len(graph.get("domains") or []) == 9
    assert len(graph.get("journeys") or []) >= 4


def test_cabang_defaults_to_sales_office_without_sell_out() -> None:
    q = "Top 10 cabang dengan penjualan terbesar di tempo"
    assert classify_cabang_grain(q) == "sales_office"


def test_cabang_sales_office_explicit() -> None:
    q = "Top 10 cabang/ sales office dengan penjualan terbesar"
    assert classify_cabang_grain(q) == "sales_office"


def test_cabang_sell_out_prefers_branch() -> None:
    q = "Top 10 cabang partner dengan penjualan sell-out B2B tertinggi"
    assert classify_cabang_grain(q) == "branch"


def test_session_metric_hints_sell_in_office() -> None:
    q = "bandingkan cabang pertama dan kelima"
    assert classify_cabang_grain(q, session_last_metric="sales_office_sell_in_value") == "sales_office"


def test_journey_sales_to_b2b() -> None:
    journey = journey_for_domains("sales", "b2b")
    assert journey is not None
    assert journey.get("dataset") == "sales_b2b_material_month"


def test_resolve_top_cabang_uses_sales_office_metric() -> None:
    ctx = SemanticContextService()
    resolution = ctx.resolve("Top 10 cabang/ sales office dengan penjualan terbesar di tempo")
    assert resolution["status"] == "resolved"
    assert resolution["metric"] == "sales_office_sell_in_value"


def test_inquiry_brief_includes_business_context() -> None:
    brief = build_inquiry_brief(
        "Hitung service level di cabang tempo",
        semantic_resolution={"status": "resolved", "metric": "sales_office_service_fill_rate"},
    )
    ctx = brief.get("business_context") or {}
    assert "service_level" in (ctx.get("detected_domains") or [])


def test_detect_multi_domain_stock_and_sales() -> None:
    domains = detect_domain_ids("stok gudang tempo vs penjualan sell-in per material")
    assert "stock_tempo" in domains
    assert "sales" in domains


def test_alfamart_penjualan_detects_b2b_and_partner_scope() -> None:
    q = "Top 10 total penjualan berdasarkan cabang di Alfamart"
    domains = detect_domain_ids(q)
    assert "b2b" in domains
    ctx = build_business_context(q)
    scope = ctx.get("partner_scope") or {}
    assert scope.get("b2b")
    assert classify_cabang_grain(q) == "branch"


def test_governed_intent_top_products_q01() -> None:
    hit = try_governed_intent_route("Top 10 produk dengan penjualan terbesar di Tempo")
    assert hit is not None
    assert hit["metric"] == "material_sell_in_value"
    assert hit["dimensions"] == ["material"]


def test_governed_intent_top_dc_q05() -> None:
    hit = try_governed_intent_route("Top 10 DC Alfamart dengan penjualan tertinggi")
    assert hit is not None
    assert hit["metric"] == "b2b_branch_sell_out_value"


def test_governed_intent_pareto_q10() -> None:
    hit = try_governed_intent_route("Bantu jelaskan pareto penjualan")
    assert hit is not None
    assert hit["metric"] == "material_sell_in_value"


def test_q09_picking_unloading_clarification() -> None:
    q = (
        "Analisa data unloading dan picking dan berikan Analisa dan perbandingan "
        "dengan Industri standard"
    )
    hit = try_clarification_intent(q)
    assert hit is not None
    assert hit["status"] == "needs_clarification"
    metrics = {opt["metric"] for opt in hit.get("options") or []}
    assert metrics == {"average_picking_minutes", "average_unloading_minutes"}
    resolution = SemanticContextService().resolve(q)
    assert resolution["status"] == "needs_clarification"
    assert resolution.get("reason") == "warehouse_ops_dual_metric"


def test_b3_questions_resolve_via_context() -> None:
    ctx = SemanticContextService()
    for question, metric in (
        ("Top 10 produk dengan penjualan terbesar di Tempo", "material_sell_in_value"),
        ("Top 10 DC Alfamart dengan penjualan tertinggi", "b2b_branch_sell_out_value"),
        ("Bantu jelaskan pareto penjualan", "material_sell_in_value"),
    ):
        resolution = ctx.resolve(question)
        assert resolution.get("status") == "resolved", question
        assert resolution.get("metric") == metric, question

"""Phase B3: management question set — routing + resolver smoke (no LLM/Impala)."""

from __future__ import annotations

from app.core.config import Settings
from app.semantic.context import SemanticContextService
from app.services.ask_data_routing import resolve_ask_data_route

QUESTIONS = [
    "Top 10 produk dengan penjualan terbesar di Tempo",
    "Top 10 cabang/ sales office dengan penjualan terbesar di tempo",
    "Top 10 DC Alfamart dengan penjualan tertinggi",
    "Cek stok produk A di toko alfamart dan bandingkan dengan stok di DC",
    "Bantu jelaskan pareto penjualan",
]


def _settings() -> Settings:
    return Settings(_env_file=None, ask_data_routing="auto", local_agent_primary=False)


def test_management_top_and_dc_questions_route_to_v3() -> None:
    s = _settings()
    ctx = SemanticContextService(s.project_root / s.ossie_project_id)
    for q in QUESTIONS:
        resolution = ctx.resolve(q)
        route = resolve_ask_data_route(q, s, semantic_resolution=resolution)
        assert route in ("v3", "ossie"), q


def test_top_penjualan_cabang_alfamart_question_mark_no_branch_filter() -> None:
    ctx = SemanticContextService()
    question = "top penjualan cabang Alfamart?"
    resolution = ctx.resolve(question)
    assert resolution.get("metric") == "b2b_branch_sell_out_value"
    sql = ctx.compile_governed(
        str(resolution["metric"]),
        question,
        resolution.get("dimensions"),
    )
    assert "alfamart" not in sql.casefold()
    assert "ORDER BY metric_value DESC" in sql
    assert "LIMIT 10" in sql


def test_alfamart_branch_ranking_sql_does_not_filter_branch_to_alfamart_label() -> None:
    ctx = SemanticContextService()
    question = "Top 10 total penjualan berdasarkan cabang di Alfamart"
    resolution = ctx.resolve(question)
    assert resolution.get("metric") == "b2b_branch_sell_out_value"
    sql = ctx.compile_governed(
        str(resolution["metric"]),
        question,
        resolution.get("dimensions"),
    )
    assert "d.branch = 'di alfamart'" not in sql.casefold()
    assert "d.branch = 'alfamart'" not in sql.casefold()
    assert "GROUP BY d.branch" in sql
    assert "LIMIT 10" in sql


def test_alfamart_branch_ranking_with_q4_period_not_branch_filter() -> None:
    ctx = SemanticContextService()
    question = "Top 10 total penjualan berdasarkan cabang di Alfamart Q4 2024"
    resolution = ctx.resolve(question)
    assert resolution.get("metric") == "b2b_branch_sell_out_value"
    sql = ctx.compile_governed(
        str(resolution["metric"]),
        question,
        resolution.get("dimensions"),
    )
    assert "alfamart" not in sql.casefold()
    assert "LIMIT 10" in sql


def test_b3_q01_q05_q10_resolve_sell_in_or_b2b_via_domain_graph() -> None:
    s = _settings()
    ctx = SemanticContextService(s.project_root / s.ossie_project_id)
    cases = [
        ("Top 10 produk dengan penjualan terbesar di Tempo", "material_sell_in_value"),
        ("Top 10 DC Alfamart dengan penjualan tertinggi", "b2b_branch_sell_out_value"),
        (
            "mau tau dong top 10 total penjualn berdasarkan cabang di alfamart",
            "b2b_branch_sell_out_value",
        ),
        ("Bantu jelaskan pareto penjualan", "material_sell_in_value"),
    ]
    for question, metric in cases:
        resolution = ctx.resolve(question)
        assert resolution.get("status") == "resolved", question
        assert resolution.get("metric") == metric, question
        assert resolve_ask_data_route(question, s, semantic_resolution=resolution) == "ossie"


def test_fill_rate_question_resolves_or_clarifies_without_crash() -> None:
    s = _settings()
    ctx = SemanticContextService(s.project_root / s.ossie_project_id)
    q = "Hitung service level/ fill rate di cabang tempo dan urutkan SL terjelek"
    resolution = ctx.resolve(q)
    assert resolution.get("status") in ("resolved", "fallback", "needs_clarification", "unsupported")

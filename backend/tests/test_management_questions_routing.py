"""Phase B3: management question set — routing + resolver smoke (no LLM/Impala)."""

from __future__ import annotations

from app.core.config import Settings
from app.semantic.context import SemanticContextService
from app.services.ask_data_routing import resolve_ask_data_route

QUESTIONS = [
    "Top 10 produk dengan penjualan terbesar di Reference",
    "Top 10 cabang/ sales office dengan penjualan terbesar di reference",
    "Top 10 DC Acme dengan penjualan tertinggi",
    "Cek stok produk A di toko acme dan bandingkan dengan stok di DC",
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


def test_fill_rate_question_resolves_or_clarifies_without_crash() -> None:
    s = _settings()
    ctx = SemanticContextService(s.project_root / s.ossie_project_id)
    q = "Hitung service level/ fill rate di cabang reference dan urutkan SL terjelek"
    resolution = ctx.resolve(q)
    assert resolution.get("status") in ("resolved", "fallback", "needs_clarification", "unsupported")

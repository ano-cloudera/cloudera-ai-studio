import pytest

from app.semantic.context import SemanticContextService
from app.services.analysis_enrichment import (
    detect_analysis_mode,
    enrich_pareto_rows,
    wants_contribution_analysis,
)
from app.services.cross_domain_compare import try_resolve_cross_domain


def test_wants_contribution_detects_kumulatif_and_kontribusi() -> None:
    assert wants_contribution_analysis("Top 10 penagihan kontribusi persen dan nilai kumulatif Nov 2024")
    assert detect_analysis_mode(
        "kontribusi penagihan material November 2024",
        "material_sell_in_value",
    ) == "pareto_contribution"


def test_enrich_pareto_rows_adds_percent_columns() -> None:
    rows = [
        {"material": "A", "metric_value": 40},
        {"material": "B", "metric_value": 30},
    ]
    enriched, columns = enrich_pareto_rows(rows, 100.0)
    assert enriched[0]["contribution_pct"] == 40.0
    assert enriched[0]["cumulative_pct"] == 40.0
    assert enriched[1]["cumulative_pct"] == 70.0
    assert "contribution_pct" in columns


def test_company_total_aggregate_sql_has_no_group_by() -> None:
    service = SemanticContextService()
    q = "Top 10 material penagihan grosir November 2024 kontribusi kumulatif"
    sql = service.compile_governed(
        "material_sell_in_value",
        q,
        [],
        company_total_aggregate=True,
    )
    assert "GROUP BY" not in sql
    assert "LIMIT 1" in sql


def test_pareto_penagihan_skips_cross_domain_sell_out_ratio() -> None:
    q = (
        "Top 10 produk nilai penagihan grosir November 2024, kontribusi persen "
        "dan nilai kumulatif sekaligus analisa penggerak"
    )
    assert try_resolve_cross_domain(q) is None
    resolution = SemanticContextService().resolve(q)
    assert resolution["status"] == "resolved"
    assert resolution["metric"] == "material_sell_in_value"

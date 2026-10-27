"""Phase C2: DC Top-N stock compiles with dcname grain."""

from __future__ import annotations

import re

from app.core.config import Settings
from app.semantic.context import SemanticContextService


def test_dc_penumpukan_compiles_group_by_dcname() -> None:
    settings = Settings(_env_file=None)
    ctx = SemanticContextService(settings.project_root / settings.ossie_project_id)
    q = (
        "Tampilkan 10 DC dengan penumpukan stok produk yang tertinggi, "
        "lalu analisa apakah ada yang bisa kita lakukan untuk memperbaiki situasi tersebut"
    )
    resolution = ctx.resolve(q)
    assert resolution.get("status") == "resolved"
    assert resolution.get("metric") == "sat_dc_stock_quantity"
    sql = ctx.compile_governed("sat_dc_stock_quantity", q, ["dcname"])
    assert "dcname" in sql.lower()
    assert "group by" in sql.lower()
    assert "order by" in sql.lower()
    assert "limit 10" in sql.lower()
    assert "dengan" not in sql.lower()
    assert "mana" not in sql.lower()


def test_dc_partner_top_n_compiles_without_partner_predicate() -> None:
    settings = Settings(_env_file=None)
    ctx = SemanticContextService(settings.project_root / settings.ossie_project_id)
    q = "maksud saya stok di DC partner, top 10 DC Alfamart Q4 2024"
    resolution = ctx.resolve(q)
    assert resolution.get("metric") == "sat_dc_stock_quantity"
    sql = ctx.compile_governed("sat_dc_stock_quantity", q, resolution.get("dimensions"))
    assert "dcname" in sql.lower()
    assert "group by" in sql.lower()
    assert "partner" not in sql.lower()


def test_fe001_sell_in_resolves_to_poc_sap_material_code() -> None:
    settings = Settings(_env_file=None)
    ctx = SemanticContextService(settings.project_root / settings.ossie_project_id)
    q = "cukup tampilkan sell-in FE001 per bulan Q4"
    sql = ctx.compile_governed("material_sell_in_quantity", q, ["calmonth", "material"])
    assert "001-00-03" in sql


def test_fe001_sell_in_per_bulan_not_single_row_lookup() -> None:
    settings = Settings(_env_file=None)
    ctx = SemanticContextService(settings.project_root / settings.ossie_project_id)
    q = "cukup tampilkan sell-in FE001 per bulan Q4"
    resolution = ctx.resolve(q)
    assert resolution.get("metric") == "material_sell_in_quantity"
    sql = ctx.compile_governed(resolution["metric"], q, resolution.get("dimensions"))
    assert re.search(r"\blimit\s+1\s*$", sql, flags=re.IGNORECASE | re.MULTILINE) is None
    assert "calmonth" in sql.lower()

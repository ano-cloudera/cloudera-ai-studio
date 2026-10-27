from app.semantic.context import SemanticContextService


def test_picking_question_compiles_with_sales_office_dimension() -> None:
    ctx = SemanticContextService()
    question = "Sales office mana dengan rata-rata durasi picking terlama Q4 2024?"
    resolution = ctx.resolve(question)
    assert resolution.get("status") == "resolved"
    assert resolution.get("metric") == "average_picking_minutes"
    sql = ctx.compile_governed(
        str(resolution["metric"]),
        question,
        resolution.get("dimensions"),
    )
    assert "d.sales_office" in sql
    assert "average_picking" in sql.casefold() or "picking" in sql.casefold()
    assert "GROUP BY d.sales_office" in sql


def test_unloading_cabang_question_compiles_sales_office() -> None:
    ctx = SemanticContextService()
    question = "Cabang mana dengan rata-rata unloading terlama Q4 2024?"
    resolution = ctx.resolve(question)
    assert resolution.get("metric") == "average_unloading_minutes"
    sql = ctx.compile_governed(
        str(resolution["metric"]),
        question,
        resolution.get("dimensions"),
    )
    assert "GROUP BY d.sales_office" in sql

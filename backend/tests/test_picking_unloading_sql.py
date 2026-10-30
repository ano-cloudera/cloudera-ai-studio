from app.semantic.context import SemanticContextService


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

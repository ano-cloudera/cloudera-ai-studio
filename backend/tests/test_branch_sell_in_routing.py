from tests.test_history import contextualize_question
from app.semantic.context import SemanticContextService


def test_sell_in_chip_after_branch_ranking_question_uses_sales_office_metric() -> None:
    history = [
        {
            "question": "bisa bantu hitungkan penjualan based on 5 branch tertinggi ?",
            "answer": {
                "direct_answer": "Apakah Anda ingin melihat Sell-In atau Sell-Out?",
                "executive_summary": "",
            },
            "rows": [],
            "strategy": "clarification",
            "status": "CLARIFICATION",
        }
    ]
    contextualized = contextualize_question("sell-in", history, clarification_choice="sell-in")
    service = SemanticContextService()
    resolution = service.resolve(contextualized)

    assert resolution["status"] == "resolved"
    assert resolution["metric"] == "sales_office_sell_in_value"
    assert resolution.get("dimensions") == ["sales_office"]
    sql = service.compile_governed(resolution["metric"], contextualized, resolution["dimensions"])
    assert "rpt_sales_office_performance_semantic" in sql
    assert "GROUP BY d.sales_office" in sql
    assert "LIMIT 5" in sql


def test_top_produk_sell_out_partner_uses_material_sell_out_metric() -> None:
    ctx = SemanticContextService()
    q = "Top 10 produk sell-out partner dengan nilai tertinggi Q4 2024"
    r = ctx.resolve(q)
    assert r.get("status") == "resolved"
    assert r.get("metric") == "material_sell_out_value"


def test_branch_ranking_with_sell_out_prefers_b2b_branch_metric() -> None:
    question = "Top 5 branch penjualan sell-out partner tertinggi Q4"
    resolution = SemanticContextService().resolve(question)

    assert resolution["status"] == "resolved"
    assert resolution["metric"] == "b2b_branch_sell_out_value"
    assert "branch" in (resolution.get("dimensions") or [])

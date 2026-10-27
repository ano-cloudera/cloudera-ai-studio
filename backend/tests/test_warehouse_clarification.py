"""Q09 picking/unloading chip → governed resolve."""

from tests.test_history import contextualize_question
from app.semantic.context import SemanticContextService

Q09 = (
    "Analisa data unloading dan picking dan berikan Analisa dan perbandingan "
    "dengan Industri standard"
)
WAREHOUSE_CLARIFY_ANSWER = (
    "Picking dan Unloading adalah dua metrik operasional gudang terpisah "
    "(durasi rata-rata per sales office, Q4 2024)."
)


def test_q09_chip_picking_merges_and_resolves() -> None:
    history = [
        {
            "question": Q09,
            "answer": {"direct_answer": WAREHOUSE_CLARIFY_ANSWER, "executive_summary": ""},
            "rows": [],
            "strategy": "clarification",
            "status": "CLARIFICATION",
        }
    ]
    chip = "Analisa durasi picking per sales office Q4 2024"
    contextualized = contextualize_question(chip, history, clarification_choice="picking")
    assert Q09 in contextualized
    assert "klarifikasi pengguna" in contextualized.casefold()

    resolution = SemanticContextService().resolve(contextualized)
    assert resolution["status"] == "resolved"
    assert resolution["metric"] == "average_picking_minutes"
    assert resolution.get("dimensions") == ["sales_office"]


def test_q09_chip_unloading_merges_and_resolves() -> None:
    history = [
        {
            "question": Q09,
            "answer": {"direct_answer": WAREHOUSE_CLARIFY_ANSWER, "executive_summary": ""},
            "strategy": "clarification",
            "status": "CLARIFICATION",
            "rows": [],
        }
    ]
    chip = "Analisa durasi unloading per sales office Q4 2024"
    contextualized = contextualize_question(chip, history, clarification_choice="unloading")
    resolution = SemanticContextService().resolve(contextualized)
    assert resolution["status"] == "resolved"
    assert resolution["metric"] == "average_unloading_minutes"

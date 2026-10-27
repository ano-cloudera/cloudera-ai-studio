"""Apply TurnUnderstanding (simulated LLM) to pipeline questions."""

from app.services.conversational import TurnUnderstanding
from app.services.question_contextualize import apply_turn_understanding, resolve_question_for_pipeline


def _u(**kwargs) -> TurnUnderstanding:
    base = {
        "is_conversational": False,
        "attach_domain_catalog": False,
        "pipeline_question": kwargs.pop("pipeline_question", ""),
        "clarification_choice": "",
        "referential_follow_up": False,
    }
    base.update(kwargs)
    if not base["pipeline_question"]:
        base["pipeline_question"] = kwargs.get("_raw", "")
    return TurnUnderstanding.model_validate(base)


def test_sell_out_clarification_merge() -> None:
    history = [
        {
            "question": "Top 10 DC Alfamart dengan penjualan tertinggi",
            "answer": {
                "direct_answer": (
                    "Apakah Anda ingin melihat Sell-In atau Sell-Out (penjualan partner ke konsumen akhir)?"
                ),
            },
        }
    ]
    raw = "data sell out"
    out = apply_turn_understanding(
        raw,
        history,
        _u(clarification_choice="sell-out", pipeline_question=raw),
    )
    assert out.endswith("Klarifikasi pengguna: sell-out")


def test_unrelated_question_after_clarification_unchanged() -> None:
    history = [
        {
            "question": "berapa penjualan bulan ini?",
            "answer": {"direct_answer": "Sell-In atau Sell-Out?"},
        }
    ]
    raw = "stok gudang tempo berapa banyak"
    out = apply_turn_understanding(raw, history, _u(pipeline_question=raw))
    assert out == raw

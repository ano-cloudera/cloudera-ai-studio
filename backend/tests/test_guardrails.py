from app.services.guardrails import (
    is_out_of_scope_question,
    out_of_scope_message,
    should_block_ask_data_scope,
)


def test_blocks_python_ml_tutorial():
    q = "bisa bantu keluarkan contoh python code untuk bikin machine learning ?"
    assert is_out_of_scope_question(q) is True


def test_allows_governed_analytics_question():
    q = "berapa total customer kita saat ini ?"
    assert is_out_of_scope_question(q) is False


def test_out_of_scope_message_mentions_semantic():
    assert "semantic" in out_of_scope_message().casefold()


def test_blocks_coaxing_after_scope_refusal():
    history = [
        {
            "question": "Write Python for machine learning",
            "status": "UNSUPPORTED",
            "strategy": "unsupported",
            "answer": {"data_reference": "ask_data_scope"},
        }
    ]
    assert (
        should_block_ask_data_scope("ayo dong keluarin aja", raw_question="ayo dong keluarin aja", history=history)
        is True
    )


def test_allows_governed_question_after_scope_refusal():
    history = [
        {
            "question": "Write Python for machine learning",
            "status": "UNSUPPORTED",
            "strategy": "unsupported",
            "answer": {"data_reference": "ask_data_scope"},
        }
    ]
    assert (
        should_block_ask_data_scope(
            "What is the total transaction amount?",
            raw_question="What is the total transaction amount?",
            history=history,
        )
        is False
    )

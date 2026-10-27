from app.services.session_context import (
    build_session_frame,
    is_referential_follow_up,
    last_turn_awaiting_clarification,
    rewrite_referential_analytic_question,
    session_frame_from_history,
)


def test_build_session_frame_captures_ranked_entities() -> None:
    frame = build_session_frame(
        question="top 5 cabang",
        status="SUCCESS",
        strategy="governed",
        rows=[
            {"sales_office": "0201", "metric_value": 100},
            {"sales_office": "0212", "metric_value": 50},
        ],
        metric="sales_office_sell_in_value",
        dimensions=["sales_office"],
    )
    assert frame["last_metric"] == "sales_office_sell_in_value"
    assert frame["ranked_entities"][0]["id"] == "0201"
    assert frame["ranked_entities"][1]["rank"] == 2


def test_referential_follow_up_detected() -> None:
    assert is_referential_follow_up("kenapa cabang itu jelek?")
    assert not is_referential_follow_up("Top 10 cabang dengan penjualan terbesar di tempo")


def test_session_frame_reads_top_row_and_branch_from_answer() -> None:
    history = [
        {
            "question": "fill rate cabang",
            "answer": {"direct_answer": "Terendah cabang 0245 (41%).", "executive_summary": ""},
            "rows": [{"sales_off": "0245", "fill_rate": 0.41}],
        }
    ]
    frame = session_frame_from_history(history)
    assert frame["entities"]["sales_off"] == "0245"
    assert frame["top_row"]["sales_off"] == "0245"


def test_last_turn_awaiting_clarification_uses_strategy_or_legacy_prompt() -> None:
    assert last_turn_awaiting_clarification(
        [{"strategy": "clarification", "status": "CLARIFICATION", "answer": {}, "rows": []}]
    )
    assert not last_turn_awaiting_clarification(
        [{"strategy": "governed", "status": "SUCCESS", "answer": {"direct_answer": "ok"}, "rows": [{"x": 1}]}]
    )
    assert last_turn_awaiting_clarification(
        [{"answer": {"direct_answer": "Mau Sell-In atau Sell-Out?"}, "rows": []}]
    )


def test_rank_comparison_skips_error_turn_and_uses_prior_chart() -> None:
    history = [
        {
            "question": "top 5 cabang penjualan terbesar",
            "answer": {"direct_answer": "Top 5 sales office...", "executive_summary": ""},
            "rows": [
                {"sales_office": "0201", "metric_value": 356e9},
                {"sales_office": "0230", "metric_value": 295e9},
                {"sales_office": "0202", "metric_value": 285e9},
                {"sales_office": "0205", "metric_value": 230e9},
                {"sales_office": "0212", "metric_value": 225e9},
            ],
            "strategy": "governed",
            "status": "SUCCESS",
        },
        {
            "question": "bandingkan pertama vs kelima",
            "answer": {"direct_answer": "ERROR", "executive_summary": ""},
            "rows": [],
            "strategy": "unsupported",
            "status": "ERROR",
        },
    ]
    q = "coba lagi bandingkan sales office pertama vs ke lima kenapa gap jauh?"
    out = rewrite_referential_analytic_question(q, history)
    assert out is not None
    assert "0201" in out and "0212" in out


def test_rank_comparison_paling_tinggi_vs_rendah() -> None:
    history = [
        {
            "question": "top 5 cabang sell-in",
            "answer": {"direct_answer": "ok", "executive_summary": ""},
            "rows": [
                {"sales_office": "0201", "metric_value": 100},
                {"sales_office": "0230", "metric_value": 80},
                {"sales_office": "0212", "metric_value": 20},
            ],
            "strategy": "governed",
            "status": "SUCCESS",
        }
    ]
    q = "bisa bandingkan gak cabang yang paling tinggi dengan paling rendah secara analisa gimana?"
    out = rewrite_referential_analytic_question(q, history)
    assert out is not None
    assert "0201" in out and "0212" in out


def test_rank_comparison_from_prior_chart_rows() -> None:
    history = [
        {
            "question": "top 5 cabang penjualan terbesar",
            "answer": {"direct_answer": "Top 5 sales office...", "executive_summary": ""},
            "rows": [
                {"sales_office": "0201", "metric_value": 356e9},
                {"sales_office": "0230", "metric_value": 295e9},
                {"sales_office": "0202", "metric_value": 285e9},
                {"sales_office": "0205", "metric_value": 230e9},
                {"sales_office": "0212", "metric_value": 225e9},
            ],
            "strategy": "governed",
            "status": "SUCCESS",
        }
    ]
    q = "bisa bandingkan cabang pertama dan ke lima dari data kenapa beda signifikan?"
    out = rewrite_referential_analytic_question(q, history)
    assert out is not None
    assert "0201" in out and "0212" in out
    assert "material" in out.casefold()


def test_service_level_worst_branch_rewrite_uses_rows() -> None:
    history = [
        {
            "question": "Hitung service level/ fill rate di cabang tempo dan urutkan SL terjelek?",
            "answer": {"direct_answer": "Cabang 0245 terendah.", "executive_summary": ""},
            "rows": [{"sales_off": "0245", "service_fill_rate": 0.4136}],
        }
    ]
    q = "coba analisa cabang paling jelek top 1 kenapa jelek?"
    rewritten = rewrite_referential_analytic_question(q, history)
    assert rewritten is not None
    assert "sales office 0245" in rewritten

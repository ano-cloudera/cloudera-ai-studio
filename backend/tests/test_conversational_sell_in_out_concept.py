from app.services.conversational import (
    _is_analytic_escape_from_clarification,
    _is_capability_meta_question,
    _is_capability_overview,
    _is_promo_proxy_explain_follow_up,
    _is_sell_in_vs_sell_out_concept,
)


def test_detects_management_concept_question() -> None:
    q = "Halo, apa bedanya sell-in Tempo dan sell-out Alfamart untuk tim manajemen?"
    assert _is_sell_in_vs_sell_out_concept(q) is True


def test_does_not_hijack_analytic_ranking() -> None:
    q = "Top 10 sell-in Tempo vs sell-out Alfamart Q4 2024"
    assert _is_sell_in_vs_sell_out_concept(q) is False


def test_detects_capability_overview_question() -> None:
    q = "Halo, data apa saja yang bisa ditanyakan untuk review manajemen Q4 di sistem ini?"
    assert _is_capability_overview(q) is True


def test_detects_capability_follow_up_after_data_turn() -> None:
    q = "terus kamu bisa bantu apa lagi selain data ini?"
    assert _is_capability_meta_question(q) is True


def test_detects_kamu_bisa_apa_lagi_ya() -> None:
    assert _is_capability_meta_question("kamu bisa apa lagi ya") is True


def test_analytic_escape_after_clarification() -> None:
    q = "cukup tampilkan sell-in FE001 per bulan Q4"
    assert _is_analytic_escape_from_clarification(q) is True


def test_promo_proxy_phrase_does_not_hijack_ranked_uplift_follow_up() -> None:
    history = [
        {
            "session_frame": {
                "last_metric": "promo_observation_count",
                "analysis_context": {"last_metric": "promo_observation_count"},
            }
        }
    ]
    q = "status dominan dari jawaban tadi, top 3 material by revenue uplift proxy"
    assert _is_promo_proxy_explain_follow_up(q, history) is False

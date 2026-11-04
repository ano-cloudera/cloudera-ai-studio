"""Fresh questions after a table must not be turned into 'the first row of that table' (found in the PDF review)."""
from __future__ import annotations

import pytest

from app.services.follow_up import _resolve_follow_up_plan, build_follow_up_rewrite, plan_follow_up
from app.services.session_context import is_referential_follow_up, names_own_period

CTX = {
    "last_metric": "total_orders",
    "last_question": "How many orders do we get per month?",
    "last_dimensions": ["fulfillment_orders_order_date"],
    "active_grain": "fulfillment_orders_order_date",
    "result_catalog": [{"id": "2026-01-01T00:00:00", "entity_type": "fulfillment_orders_order_date", "dimension": "fulfillment_orders_order_date", "rank": 1}],
}


class EveryQuestionIsAFollowUp:
    """A small model that calls any question a follow-up on rank 1."""

    referential_follow_up = True
    follow_up_entity_id = None
    follow_up_entity_dimension = None
    follow_up_rank = 1
    follow_up_material_drill = False
    follow_up_top_n = None
    pipeline_question = ""


FRESH = [
    "berapa total order di bulan maret 2026 ini ?",
    "Total orders from March to May",
    "Bandingkan late delivery Sumatera Utara bulan Maret dengan bulan Juni",
    "Which region has the highest late delivery rate?",
    "Berapa late delivery rate di kalimantn timur?",
    "Which carriers have a late rate above overall?",
    "Kenapa Kalimantan Timur sering terlambat?",
    "Why is Kalimantan Timur late so often?",
]
FOLLOW_UPS = ["tampilkan detail itu", "rincian per bulan untuk yang tertinggi tadi", "top 1 saja"]


@pytest.mark.parametrize("question", FRESH)
def test_a_fresh_question_is_never_a_follow_up_even_when_the_model_says_so(question: str) -> None:
    assert _resolve_follow_up_plan(question, CTX, EveryQuestionIsAFollowUp()) is None


@pytest.mark.parametrize("question", FOLLOW_UPS)
def test_a_question_that_points_at_the_last_result_still_is(question: str) -> None:
    assert _resolve_follow_up_plan(question, CTX, EveryQuestionIsAFollowUp()) is not None


def test_pointing_words_match_whole_words_only() -> None:
    assert not is_referential_follow_up("What is the weekly trend for the mini dataset?")  # "ini" inside "mini"
    assert is_referential_follow_up("lihat yang ini saja")
    assert names_own_period("total order di bulan maret 2026") and not names_own_period("tampilkan detail itu")


def test_the_rewrite_no_longer_injects_a_period_that_the_user_never_wrote() -> None:
    plan = plan_follow_up("rincian per bulan untuk yang tertinggi tadi", CTX)
    assert plan is not None
    assert "Q4 2024" not in build_follow_up_rewrite("rincian per bulan untuk yang tertinggi tadi", CTX, plan)

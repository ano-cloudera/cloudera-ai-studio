"""Every "You could ask next" chip is a question the assistant can answer when it is clicked."""
from __future__ import annotations

from app.ask_data.follow_up_suggestions import built_suggestions, settle_follow_ups
from replay_support import build_context


def test_a_paraphrase_that_names_no_metric_is_replaced_by_one_that_does() -> None:
    ctx = build_context()
    settled = settle_follow_ups(
        ["Berapa tingkat keterlambatan pengiriman di Jawa Timur?", "Late rate per carrier di Jawa Timur"],
        semantic_context=ctx,
        asked="Late delivery rate per region",
        metric="late_delivery_rate",
        dimensions=["delivery_shipments_region_name"],
        language="en",
    )
    assert settled[0] == "Late rate per carrier di Jawa Timur"
    assert "Berapa tingkat keterlambatan pengiriman di Jawa Timur?" not in settled
    assert len(settled) == 3
    assert all(ctx.registry.resolve_metric(q)["status"] == "resolved" for q in settled)


def test_built_suggestions_use_an_unused_breakdown_and_the_month_never_an_id() -> None:
    built = built_suggestions(build_context(), metric="late_delivery_rate", dimensions=["delivery_shipments_region_name"], language="en")
    assert built[:2] == ["Late Delivery Rate by carrier", "Late Delivery Rate per month"]
    assert not any(" id" in q or "shipment" in q.split(" by ")[-1] for q in built)


def test_the_question_just_asked_is_not_suggested_again() -> None:
    settled = settle_follow_ups(
        ["Late Delivery Rate by carrier"], semantic_context=build_context(), asked="late delivery rate by carrier",
        metric="late_delivery_rate", dimensions=["delivery_shipments_carrier"], language="en",
    )
    assert "Late Delivery Rate by carrier" not in settled

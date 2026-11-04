from __future__ import annotations

from app.ask_data.calculation_note import build_calculation_note, readable_name

DEF = {"base_dataset": "delivery_shipments", "expression": "COUNT(CASE WHEN delivery_shipments.is_late THEN 1 END) * 100.0 / COUNT(delivery_shipments.shipment_id)", "description": "Late delivery rate"}


def test_names_are_made_readable() -> None:
    assert readable_name("fulfillment_orders_region_name", "fulfillment_orders") == "region name"
    assert readable_name("carrier") == "carrier"


def test_a_governed_answer_lists_metric_formula_filters_period_and_source() -> None:
    sql = (
        "SELECT d.region_name AS delivery_shipments_region_name, COUNT(d.shipment_id) AS metric_value "
        "FROM \"hive\".\"default\".\"delivery_shipments\" d "
        "WHERE d.carrier = 'NusaCargo' AND d.ship_date >= DATE '2026-03-01' AND d.ship_date < DATE '2026-06-01' "
        "GROUP BY d.region_name ORDER BY metric_value DESC"
    )
    note = build_calculation_note(
        strategy="governed", sql=sql, metric="late_delivery_rate", definition=DEF,
        dimensions=["delivery_shipments_region_name"], drill=None,
    )
    assert note is not None and note.kind == "governed"
    assert note.breakdown == ["region name"]
    assert note.filters == ["carrier: NusaCargo"]
    assert note.period == "2026-03-01 to 2026-05-31"
    assert note.source == ["delivery_shipments"]
    assert note.formula.startswith("COUNT(CASE WHEN is_late") and "d." not in note.formula and "delivery_shipments." not in note.formula
    assert "region name" in note.summary and "2026-03-01 to 2026-05-31" in note.summary


def test_a_month_breakdown_says_month() -> None:
    sql = "SELECT DATE_TRUNC('month', CAST(d.order_date AS TIMESTAMP)) AS orders_order_date, COUNT(d.order_id) AS metric_value FROM \"hive\".\"default\".\"fulfillment_orders\" d GROUP BY DATE_TRUNC('month', CAST(d.order_date AS TIMESTAMP))"
    note = build_calculation_note(strategy="governed", sql=sql, metric="total_orders", definition={"base_dataset": "orders"}, dimensions=["orders_order_date"], drill=None)
    assert note.breakdown == ["month of order date"]


def test_a_period_comparison_is_described_from_the_drill_state() -> None:
    sql = "SELECT COUNT(d.shipment_id) AS metric_value FROM \"hive\".\"default\".\"delivery_shipments\" d WHERE d.ship_date >= DATE '2026-03-01' AND d.ship_date < DATE '2026-06-01'"
    drill = {"kind": "periods", "meta": {"previous": "2026-03 to 2026-05", "current": "2026-06 to 2026-08"}, "queries": [{"sql": sql, "dimensions": []}, {"sql": sql, "dimensions": []}]}
    note = build_calculation_note(strategy="governed", sql=sql, metric="late_delivery_rate", definition=DEF, dimensions=[], drill=drill)
    assert note.kind == "comparison" and note.period == "2026-03 to 2026-05 vs 2026-06 to 2026-08"
    assert "later minus earlier" in note.comparison


def test_nothing_executed_means_no_note_and_fallback_has_no_formula() -> None:
    assert build_calculation_note(strategy="governed", sql=None, metric=None, definition=None, dimensions=None, drill=None) is None
    note = build_calculation_note(strategy="sql_fallback", sql='SELECT 1 FROM "hive"."default"."v_x" d WHERE d.a = 1', metric=None, definition=None, dimensions=None, drill=None)
    assert note.kind == "fallback" and note.formula is None and note.source == ["v_x"]


def test_the_scope_sentence_says_what_the_figures_cover_in_the_language_of_the_question() -> None:
    from app.ask_data.calculation_note import _scope_sentence

    assert _scope_sentence("2026-03-01 to 2026-03-31", ["fulfillment_orders"], [], [], "en") == (
        "Covers 2026-03-01 to 2026-03-31 in fulfillment_orders, with no breakdown or filter applied."
    )
    assert _scope_sentence(None, ["delivery_shipments"], ["region name: Sumatera Utara"], ["carrier"], "en") == (
        "Covers all dates in delivery_shipments, filtered to region name: Sumatera Utara, broken down by carrier."
    )
    assert _scope_sentence("2026-03-01 to 2026-03-31", ["fulfillment_orders"], [], [], "id") == (
        "Mencakup 2026-03-01 sampai 2026-03-31 pada fulfillment_orders, tanpa pemecahan atau filter."
    )

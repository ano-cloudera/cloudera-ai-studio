"""What the answer shows: business column names, a chart whose series is a category, typo guesses only for real values."""
from __future__ import annotations

from app.ask_data.chart_inference import repair_chart_spec
from app.ask_data.column_labels import column_labels
from app.ask_data.value_filters import fuzzy_matches
from app.core.models import ChartSpec
from replay_support import build_context


def test_columns_are_named_in_business_words() -> None:
    labels = column_labels(
        ["delivery_shipments_region_name", "delivery_shipments_carrier", "delivery_shipments_ship_date", "metric_value"],
        semantic_context=build_context(),
        sql="SELECT DATE_TRUNC('month', CAST(d.ship_date AS TIMESTAMP)) ...",
        metric_label="Late Delivery Rate",
    )
    assert labels == {
        "delivery_shipments_region_name": "Region",
        "delivery_shipments_carrier": "Carrier",
        "delivery_shipments_ship_date": "Month",
        "metric_value": "Late Delivery Rate",
    }


def test_the_value_column_is_never_a_series() -> None:
    rows = [{"month": "2026-01-01T00:00:00", "metric_value": 18.8}, {"month": "2026-02-01T00:00:00", "metric_value": 28.2}]
    chart = ChartSpec(type="line", title="t", x="month", y="metric_value", series="metric_value")
    assert repair_chart_spec(chart, columns=["month", "metric_value"], rows=rows).series is None


CATALOG = {
    "carrier": ["KilatKirim", "NusaCargo", "FastExpress"],
    "delivery_status": ["Delivered", "Late", "Failed"],
    "region_name": ["Jawa Timur", "Kalimantan Timur"],
}
VOCABULARY = {"late", "delivery", "rate", "shipments", "carrier", "region", "status"}


def test_a_misspelt_metric_word_or_an_everyday_phrase_is_not_a_value() -> None:
    assert fuzzy_matches("bisa bantu keluarkan late deliveray rate di jawa timur ?", CATALOG, {"region_name": ["Jawa Timur"]}, VOCABULARY) == []
    assert fuzzy_matches("berapa banyak paket yang kita kirim?", CATALOG, {}, VOCABULARY) == []


def test_a_misspelt_value_is_still_corrected() -> None:
    matches = fuzzy_matches("late rate di kalimantn timur", CATALOG, {}, VOCABULARY)
    assert [(m.values, m.applied) for m in matches] == [(("Kalimantan Timur",), True)]

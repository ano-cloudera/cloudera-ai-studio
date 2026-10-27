from __future__ import annotations

from app.ask_data.chart_inference import infer_chart_spec_from_result, repair_chart_spec
from app.core.models import ChartSpec
from app.semantic.banking_demo_catalog import infer_banking_breakdown_dimensions


def test_infer_tipe_akun_maps_to_segment():
    allowed = {"customers_segment", "customers_city"}
    dims = infer_banking_breakdown_dimensions("Bandingkan jumlah customer per tipe akun.", allowed)
    assert dims == ["customers_segment"]


def test_repair_chart_swaps_non_numeric_y_to_metric_value():
    chart = ChartSpec(
        type="line",
        title="Trend",
        x="transactions_transaction_date",
        y="transactions_transaction_date",
    )
    rows = [
        {"transactions_transaction_date": "2026-06-01T00:00:00", "metric_value": 95},
        {"transactions_transaction_date": "2026-07-01T00:00:00", "metric_value": 118},
    ]
    fixed = repair_chart_spec(chart, columns=list(rows[0].keys()), rows=rows)
    assert fixed is not None
    assert fixed.y == "metric_value"
    assert fixed.x == "transactions_transaction_date"


def test_infer_line_chart_from_time_dimension():
    rows = [
        {"transactions_transaction_date": "2026-06-01", "metric_value": 40},
        {"transactions_transaction_date": "2026-07-01", "metric_value": 55},
    ]
    spec = infer_chart_spec_from_result(
        columns=list(rows[0].keys()),
        rows=rows,
        question="Trend jumlah transaksi per bulan",
    )
    assert spec is not None
    assert spec.type == "line"
    assert spec.y == "metric_value"

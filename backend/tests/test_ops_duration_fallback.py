from app.services.ops_duration_narrative import (
    deterministic_ops_duration_answer,
    deterministic_ops_workload_answer,
)


def test_deterministic_picking_fastest_from_first_row() -> None:
    text = deterministic_ops_duration_answer(
        "Sales office mana picking-nya paling efisien (tercepat) Q4 2024?",
        "average_picking_minutes",
        [{"sales_office": "0274", "metric_value": 12.34}],
    )
    assert text is not None
    assert "0274" in text
    assert "12.34" in text


def test_deterministic_unloading_company_wide_average() -> None:
    text = deterministic_ops_duration_answer(
        "Berapa rata-rata unloading minutes company-wide Tempo Q4 2024?",
        "average_unloading_minutes",
        [{"metric_value": 45.67}],
    )
    assert text is not None
    assert "45.67" in text
    assert "company-wide" in text.casefold()


def test_deterministic_unloading_event_count_top_office() -> None:
    text = deterministic_ops_workload_answer(
        "Berapa banyak event unloading per sales office Q4? cabang aktivitas terbanyak.",
        "unloading_event_count",
        [{"sales_office": "0260", "metric_value": 128.0}],
    )
    assert text is not None
    assert "0260" in text
    assert "128" in text


def test_deterministic_unloading_ignored_for_unrelated_metric() -> None:
    assert (
        deterministic_ops_duration_answer(
            "Sales office mana unloading-nya paling efisien?",
            "material_sell_in_value",
            [{"sales_office": "0201", "metric_value": 1}],
        )
        is None
    )

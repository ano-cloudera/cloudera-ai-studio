from app.services.rows_summary import summarize_rows


def test_a_single_value_is_stated() -> None:
    assert summarize_rows([{"metric_value": 65.0731}]) == "The result is 65.07."
    assert summarize_rows([{"metric_value": 74}]) == "The result is 74."
    assert summarize_rows([{"metric_value": 12000}], language="id") == "Hasilnya 12,000."


def test_one_group_names_the_group() -> None:
    assert summarize_rows([{"region_name": "Jawa Barat", "metric_value": 47.2}]) == "Jawa Barat: 47.20."


def test_several_groups_give_the_highest_and_lowest() -> None:
    rows = [
        {"region_name": "Bali", "metric_value": 67.8},
        {"region_name": "Jawa Barat", "metric_value": 47.2},
        {"region_name": "DKI Jakarta", "metric_value": 68.2},
    ]
    assert summarize_rows(rows) == "3 groups. Highest: DKI Jakarta (68.20); lowest: Jawa Barat (47.20)."
    assert "Tertinggi: DKI Jakarta" in summarize_rows(rows, language="id")


def test_empty_or_non_numeric_results_give_nothing() -> None:
    assert summarize_rows([]) == ""
    assert summarize_rows([{"region_name": "Bali"}]) == ""

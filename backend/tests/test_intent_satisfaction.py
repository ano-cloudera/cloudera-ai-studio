from __future__ import annotations

from types import SimpleNamespace

from app.ask_data.intent_satisfaction import (
    parse_explicit_calendar_period,
    registry_period_sql_predicate,
    validate_registry_resolution,
)


def _fake_registry(*, time_key: str = "sale_date", expr: str = "uat_sales.sale_date") -> SimpleNamespace:
    return SimpleNamespace(
        dataset_fields={
            "uat_sales": {
                time_key: {
                    "dimension": {"is_time": True},
                    "column": "sale_date",
                },
            },
        },
        ansi_expression=lambda field: expr,
    )


def test_parse_explicit_may_2024() -> None:
    period = parse_explicit_calendar_period("What is total sales in May 2024?")
    assert period is not None
    assert period.year == 2024
    assert period.month == 5


def test_parse_june_2024() -> None:
    period = parse_explicit_calendar_period("Total sales for June 2024")
    assert period is not None
    assert period.month == 6


def test_unsupported_region_blocks() -> None:
    resolution = {"status": "resolved", "metric": "total_sales", "dimensions": []}
    definition = {"base_dataset": "uat_sales", "allowed_dimensions": ["sale_date", "amount"]}
    registry = _fake_registry()
    validation = validate_registry_resolution(
        "What is total sales for Antarctica region?",
        resolution,
        definition=definition,
        registry=registry,
    )
    assert not validation.intent_complete
    assert "region" in validation.unresolved_constraints
    assert "region" in validation.user_message.casefold() or "geography" in validation.user_message.casefold()


def test_period_predicate_on_sale_date() -> None:
    registry = _fake_registry()
    sql_pred = registry_period_sql_predicate(
        "What is total sales in May 2024?",
        dataset_name="uat_sales",
        registry=registry,
    )
    assert sql_pred is not None
    assert "2024-05-01" in sql_pred
    assert "2024-06-01" in sql_pred
    assert "sale_date" in sql_pred

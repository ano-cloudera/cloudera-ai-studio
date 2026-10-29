from __future__ import annotations

from unittest.mock import MagicMock

from app.semantic_registry.metric_validation import validate_metric_draft


def _dim(entity: str, column: str, data_type: str):
    d = MagicMock()
    d.source_entity_key = entity
    d.source_column = column
    d.data_type = data_type
    return d


def test_valid_sum_numeric():
    dims = [_dim("sales", "amount", "decimal")]
    result = validate_metric_draft(
        name="Net Sales",
        business_definition="Total",
        expression="SUM(amount)",
        aggregation="sum",
        source_entity_key="sales",
        entity_keys={"sales"},
        dimensions=dims,
        existing_metric_names=set(),
    )
    assert result.valid is True
    assert not result.issues


def test_invalid_sum_text_column():
    dims = [_dim("sales", "product_name", "string")]
    result = validate_metric_draft(
        name="Bad",
        business_definition="x",
        expression="SUM(product_name)",
        aggregation="sum",
        source_entity_key="sales",
        entity_keys={"sales"},
        dimensions=dims,
        existing_metric_names=set(),
    )
    assert result.valid is False
    assert any("product_name" in i.message for i in result.issues)


def test_missing_column():
    result = validate_metric_draft(
        name="Bad",
        business_definition="x",
        expression="SUM(nonexistent_column)",
        aggregation="sum",
        source_entity_key="sales",
        entity_keys={"sales"},
        dimensions=[],
        existing_metric_names=set(),
    )
    assert result.valid is False
    assert any("nonexistent_column" in i.message for i in result.issues)


def test_duplicate_name():
    result = validate_metric_draft(
        name="Revenue",
        business_definition="x",
        expression="SUM(amount)",
        aggregation="sum",
        source_entity_key="sales",
        entity_keys={"sales"},
        dimensions=[_dim("sales", "amount", "int")],
        existing_metric_names={"revenue"},
    )
    assert result.valid is False
    assert any(i.field == "name" for i in result.issues)


def test_physical_numeric_type_wins_over_a_loose_dimension_type():
    dims = [_dim("credit_applications", "decision_time_hours", "string")]
    result = validate_metric_draft(
        name="Average Decision Time",
        business_definition="Average decision time in hours.",
        expression="AVG(decision_time_hours)",
        aggregation=None,
        source_entity_key="credit_applications",
        entity_keys={"credit_applications"},
        dimensions=dims,
        existing_metric_names=set(),
        source_entity_metadata={"physical_columns": [{"name": "decision_time_hours", "normalized_type": "FLOAT"}]},
    )
    assert result.valid is True, [i.message for i in result.issues]


def test_physical_text_type_still_blocks_a_numeric_aggregate():
    dims = [_dim("credit_applications", "region_name", "decimal")]
    result = validate_metric_draft(
        name="Bad",
        business_definition="x",
        expression="SUM(region_name)",
        aggregation="sum",
        source_entity_key="credit_applications",
        entity_keys={"credit_applications"},
        dimensions=dims,
        existing_metric_names=set(),
        source_entity_metadata={"physical_columns": [{"name": "region_name", "normalized_type": "STRING"}]},
    )
    assert result.valid is False

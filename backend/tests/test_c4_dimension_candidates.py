from __future__ import annotations

from app.connectors.metadata import ColumnInfo
from app.semantic_registry.dimension_candidates import is_dimension_candidate, suggest_dimension_candidates


def test_numeric_measure_not_candidate_by_default():
    col = ColumnInfo(name="sell_in_bill_val", native_type="decimal", normalized_type="DECIMAL")
    assert is_dimension_candidate(col) is False


def test_string_and_suffix_heuristics():
    cols = [
        ColumnInfo(name="material_code", normalized_type="STRING"),
        ColumnInfo(name="customer_id", normalized_type="INTEGER"),
        ColumnInfo(name="calmonth", normalized_type="DATE"),
    ]
    suggested = suggest_dimension_candidates(cols)
    assert {c.name for c in suggested} == {"material_code", "customer_id", "calmonth"}

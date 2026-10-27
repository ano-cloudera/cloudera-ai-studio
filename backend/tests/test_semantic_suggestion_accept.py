"""Phase 2B suggestion accept helpers."""
from __future__ import annotations

from app.services.semantic_suggestion_accept_service import _infer_aggregation, _normalize_metric_expression


def test_normalize_metric_expression_strips_entity_prefix():
    assert _normalize_metric_expression("SUM(sales.amount)") == "SUM(amount)"


def test_infer_aggregation_from_expression():
    assert _infer_aggregation("SUM(amount)") == "sum"
    assert _infer_aggregation("COUNT(id)") == "count"

"""Phase 2B suggestion accept helpers."""
from __future__ import annotations

from app.semantic.banking_demo_catalog import coerce_suggested_metric_metadata
from app.services.semantic_suggestion_accept_service import _infer_aggregation, _normalize_metric_expression


def test_normalize_metric_expression_strips_entity_prefix():
    assert _normalize_metric_expression("SUM(sales.amount)") == "SUM(amount)"


def test_infer_aggregation_from_expression():
    assert _infer_aggregation("SUM(amount)") == "sum"
    assert _infer_aggregation("COUNT(id)") == "count"


def test_coerce_suggested_banking_customer_metric():
    name, expr, definition = coerce_suggested_metric_metadata(
        key="customers_customer_id_total",
        expression="SUM(customer_id)",
        name="Suggested metric customers_customer_id_total",
    )
    assert name == "Total Customers"
    assert expr == "COUNT(DISTINCT customer_id)"
    assert "customer" in definition.casefold()

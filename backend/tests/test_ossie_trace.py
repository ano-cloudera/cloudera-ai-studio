from app.services.ossie_trace import trace_detail


def test_trace_detail_plan_query_governed_metric_only() -> None:
    detail = trace_detail(
        "plan_query",
        {"semantic_resolution": {"metric": "customers_customer_id_total", "status": "resolved"}},
    )
    assert detail == "Governed metric: customers_customer_id_total"


def test_trace_detail_validate_query_sql_preview() -> None:
    detail = trace_detail("validate_query", {"governed_sql": "SELECT COUNT(1) FROM banking_demo.customers"})
    assert detail is not None
    assert "banking_demo.customers" in detail

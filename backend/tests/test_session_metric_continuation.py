from app.semantic.context import SemanticContextService


def test_monthly_breakdown_continues_prior_gross_billing_metric() -> None:
    ctx = {"last_metric": "gross_billing_value", "last_dimensions": []}
    question = "tampilkan per bulan Oktober November Desember untuk pertanyaan tadi"
    resolution = SemanticContextService()._try_session_metric_continuation(question, ctx)
    assert resolution is not None
    assert resolution["metric"] == "gross_billing_value"
    assert resolution["matched_alias"] == "session_metric_continuation"
    assert "calmonth" in resolution["dimensions"]

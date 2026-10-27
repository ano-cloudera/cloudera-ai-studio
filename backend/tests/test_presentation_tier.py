from app.ask_data.presentation_tier import (
    attach_presentation_tier,
    compute_presentation_tier,
    tier_from_inquiry_brief,
)
from app.core.models import AnalysisOutput, AskDataResponse, ChartSpec, QueryData, Timings
from app.graph.inquiry_brief import build_inquiry_brief


def _response(**kwargs) -> AskDataResponse:
    base = AskDataResponse(
        request_id="r1",
        session_id="s1",
        status="SUCCESS",
        provider="gemini",
        model="m",
        strategy="governed",
        answer=AnalysisOutput(
            direct_answer="ok",
            executive_summary="ok",
            insights=[],
            business_implications=[],
            caveats=[],
            data_reference="ref",
        ),
        data=QueryData(columns=["total"], rows=[{"total": 31375}], row_count=1, execution_ms=5),
        chart_spec=ChartSpec(type="kpi", title="Total", y="total"),
        timings=Timings(total_ms=1),
        governed_sql="SELECT COUNT(*) FROM customers",
    )
    return base.model_copy(update=kwargs)


def test_tier1_single_kpi() -> None:
    assert compute_presentation_tier(_response()) == 1
    out = attach_presentation_tier(_response())
    assert out.presentation_tier == 1


def test_tier3_visual_chart() -> None:
    r = _response(
        chart_spec=ChartSpec(type="bar", title="By region", x="region", y="n"),
        data=QueryData(
            columns=["region", "n"],
            rows=[{"region": "a", "n": 1}, {"region": "b", "n": 2}],
            row_count=2,
            execution_ms=5,
        ),
    )
    assert compute_presentation_tier(r) == 3


def test_inquiry_brief_min_tier_for_top_10() -> None:
    brief = build_inquiry_brief("Top 10 produk dengan penjualan terbesar")
    assert brief.get("presentation_min_tier") == 3
    assert tier_from_inquiry_brief(brief) == 3


def test_brief_elevates_tier_for_ranking_question() -> None:
    r = _response(
        chart_spec=None,
        data=QueryData(columns=["x"], rows=[{"x": 1}], row_count=1, execution_ms=1),
    )
    brief = build_inquiry_brief("Top 10 DC dengan penjualan tertinggi")
    assert compute_presentation_tier(r, inquiry_brief=brief) == 3

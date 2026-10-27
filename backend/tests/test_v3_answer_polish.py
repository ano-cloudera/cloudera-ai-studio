from app.core.models import AnalysisOutput, AskDataResponse, QueryData, Timings
from app.services.v3_answer_polish import polish_v3_answer


def test_polish_strips_table_when_rows_present() -> None:
    response = AskDataResponse(
        request_id="r",
        session_id="s",
        status="SUCCESS",
        provider="gemini",
        model="m",
        strategy="governed",
        answer=AnalysisOutput(
            direct_answer="Jawaban\n\n| a | b |\n| --- | --- |\n| 1 | 2 |\n\nAnalisis\n1. First point.",
            executive_summary="same",
            insights=[],
            business_implications=[],
            caveats=[],
            data_reference="query ids",
            chart_spec=None,
        ),
        data=QueryData(columns=["a"], rows=[{"a": 1}], row_count=1),
        chart_spec=None,
        timings=Timings(total_ms=1),
    )
    polished = polish_v3_answer(response)
    assert "|" not in polished.answer.direct_answer
    assert "First point" in " ".join(polished.answer.insights) or "Analisis" in polished.answer.direct_answer

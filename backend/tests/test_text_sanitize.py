from app.core.models import AnalysisOutput
from app.services.text_sanitize import without_em_dash


def test_without_em_dash_replaces_punctuation():
    assert without_em_dash("A — B") == "A, B"
    assert without_em_dash("period—next") == "period, next"


def test_analysis_output_strips_em_dash():
    answer = AnalysisOutput(
        direct_answer="Nilai tinggi — perlu tindak lanjut",
        executive_summary="Ringkas",
        insights=[],
        business_implications=[],
        caveats=[],
        data_reference="gold.view",
        chart_spec=None,
    )
    assert "—" not in answer.direct_answer
    assert "," in answer.direct_answer

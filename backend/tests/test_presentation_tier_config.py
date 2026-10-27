from app.ask_data.presentation_tier import compute_presentation_tier
from app.ask_data.presentation_tier_config import (
    PresentationTierConfig,
    PresentationTierOverrides,
    resolve_presentation_tier_config,
)
from app.core.models import AnalysisOutput, AskDataResponse, QueryData, Timings


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
        data=QueryData(columns=["n"], rows=[{"n": i} for i in range(5)], row_count=5, execution_ms=1),
        chart_spec=None,
        timings=Timings(total_ms=1),
    )
    return base.model_copy(update=kwargs)


def test_merge_workspace_override_lowers_tier3_threshold() -> None:
    cfg = PresentationTierConfig(tier3_min_rows=5)
    assert compute_presentation_tier(_response(), config=cfg) == 3

    default_cfg = PresentationTierConfig()
    assert compute_presentation_tier(_response(), config=default_cfg) == 2


def test_resolve_merges_overrides() -> None:
    from app.core.config import Settings

    base = resolve_presentation_tier_config(Settings())
    merged = base.merge_overrides(
        PresentationTierOverrides(panel_auto_open="never", tier3_min_rows=4, tier1_show_narrative=True)
    )
    assert merged.panel_auto_open == "never"
    assert merged.tier3_min_rows == 4
    assert merged.tier1_show_narrative is True


def test_panel_auto_open_modes() -> None:
    cfg = PresentationTierConfig(panel_auto_open="always")
    assert cfg.should_auto_open_panel(1, status="SUCCESS", has_report_evidence=True)
    cfg2 = PresentationTierConfig(panel_auto_open="never")
    assert not cfg2.should_auto_open_panel(3, status="SUCCESS", has_report_evidence=True)

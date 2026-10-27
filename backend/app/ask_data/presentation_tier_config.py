"""Configurable Ask Data presentation tier (AMP / deployment profiles)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.core.config import Settings

PanelAutoOpenMode = Literal["heuristic", "always", "never"]
AudienceMode = Literal["executive", "analyst"]


class PresentationTierOverrides(BaseModel):
    """Partial overrides (workspace Ask Data settings)."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool | None = None
    panel_auto_open: PanelAutoOpenMode | None = None
    tier3_min_rows: int | None = Field(default=None, ge=1, le=10_000)
    tier3_min_insights: int | None = Field(default=None, ge=0, le=50)
    tier3_min_implications: int | None = Field(default=None, ge=0, le=50)
    rank_tier3_above_n: int | None = Field(default=None, ge=0, le=500)
    rank_min_tier: int | None = Field(default=None, ge=1, le=3)
    tier1_max_rows: int | None = Field(default=None, ge=0, le=100)
    tier1_max_columns: int | None = Field(default=None, ge=1, le=50)
    force_tier3_on_pareto: bool | None = None
    force_tier3_on_operational_analysis: bool | None = None
    force_tier3_on_visual_chart: bool | None = None
    chat_expand_tier1: bool | None = None
    chat_expand_tier2: bool | None = None
    chat_details_default_open: bool | None = None
    audience_mode: AudienceMode | None = None
    tier1_show_narrative: bool | None = None


class PresentationTierConfig(BaseModel):
    """Effective tier routing configuration."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    panel_auto_open: PanelAutoOpenMode = "heuristic"
    tier3_min_rows: int = Field(default=13, ge=1, le=10_000)
    tier3_min_insights: int = Field(default=3, ge=0, le=50)
    tier3_min_implications: int = Field(default=2, ge=0, le=50)
    rank_tier3_above_n: int = Field(default=5, ge=0, le=500)
    rank_min_tier: int = Field(default=2, ge=1, le=3)
    tier1_max_rows: int = Field(default=1, ge=0, le=100)
    tier1_max_columns: int = Field(default=2, ge=1, le=50)
    force_tier3_on_pareto: bool = True
    force_tier3_on_operational_analysis: bool = True
    force_tier3_on_visual_chart: bool = True
    chat_expand_tier1: bool = True
    chat_expand_tier2: bool = True
    chat_details_default_open: bool = False
    audience_mode: AudienceMode = "executive"
    tier1_show_narrative: bool = False

    @classmethod
    def from_settings(cls, settings: Settings) -> PresentationTierConfig:
        panel = (getattr(settings, "ask_data_panel_auto_open", "heuristic") or "heuristic").strip().lower()
        if panel not in {"heuristic", "always", "never"}:
            panel = "heuristic"
        return cls(
            enabled=bool(getattr(settings, "ask_data_presentation_tier_enabled", True)),
            panel_auto_open=panel,  # type: ignore[arg-type]
            tier3_min_rows=int(getattr(settings, "ask_data_tier3_min_rows", 13)),
            tier3_min_insights=int(getattr(settings, "ask_data_tier3_min_insights", 3)),
            tier3_min_implications=int(getattr(settings, "ask_data_tier3_min_implications", 2)),
            rank_tier3_above_n=int(getattr(settings, "ask_data_rank_tier3_above_n", 5)),
            rank_min_tier=int(getattr(settings, "ask_data_rank_min_tier", 2)),
            tier1_max_rows=int(getattr(settings, "ask_data_tier1_max_rows", 1)),
            tier1_max_columns=int(getattr(settings, "ask_data_tier1_max_columns", 2)),
            force_tier3_on_pareto=bool(getattr(settings, "ask_data_force_tier3_pareto", True)),
            force_tier3_on_operational_analysis=bool(
                getattr(settings, "ask_data_force_tier3_operational", True)
            ),
            force_tier3_on_visual_chart=bool(getattr(settings, "ask_data_force_tier3_chart", True)),
            chat_expand_tier1=bool(getattr(settings, "ask_data_chat_expand_tier1", True)),
            chat_expand_tier2=bool(getattr(settings, "ask_data_chat_expand_tier2", True)),
            chat_details_default_open=bool(getattr(settings, "ask_data_chat_details_default_open", False)),
            audience_mode=_parse_audience_mode(getattr(settings, "ask_data_audience_mode", "executive")),
            tier1_show_narrative=bool(getattr(settings, "ask_data_tier1_show_narrative", False)),
        )

    def merge_overrides(self, overrides: PresentationTierOverrides | None) -> PresentationTierConfig:
        if overrides is None:
            return self
        data = self.model_dump()
        for key, value in overrides.model_dump(exclude_none=True).items():
            data[key] = value
        return PresentationTierConfig.model_validate(data)

    def should_auto_open_panel(self, tier: int, *, status: str, has_report_evidence: bool) -> bool:
        if status != "SUCCESS" or not has_report_evidence:
            return False
        if self.panel_auto_open == "never":
            return False
        if self.panel_auto_open == "always":
            return True
        return tier == 3

    def model_public(self) -> dict[str, Any]:
        return self.model_dump()


def _parse_audience_mode(raw: str) -> AudienceMode:
    value = (raw or "executive").strip().lower()
    return "analyst" if value == "analyst" else "executive"


def resolve_presentation_tier_config(
    settings: Settings,
    *,
    workspace_overrides: PresentationTierOverrides | None = None,
) -> PresentationTierConfig:
    return PresentationTierConfig.from_settings(settings).merge_overrides(workspace_overrides)

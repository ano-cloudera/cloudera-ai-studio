"""Workspace-level switches for the optional parts of the UI (menus and pages).

The deployment decides the defaults (NEXT_PUBLIC_FEATURE_* at build time); a workspace can switch some of them off or on
without a new build. This only hides menus and pages: the API behind them stays available, so it is not an access control.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator

FEATURE_OVERRIDES_KEY = "feature_overrides"

# Names match the Frontend (appConfig.features).
SWITCHABLE_FEATURES = frozenset({"documents", "connectors", "prompts", "skills", "semanticLayer", "usage"})
# Always on: without them there is nothing to use, or no way to switch anything back on.
LOCKED_FEATURES = frozenset({"askData", "settings", "aiModelRegistry"})


class FeatureOverrides(BaseModel):
    model_config = ConfigDict(extra="forbid")

    overrides: dict[str, bool] = Field(default_factory=dict)

    @field_validator("overrides")
    @classmethod
    def only_switchable(cls, value: dict[str, bool]) -> dict[str, bool]:
        locked = sorted(set(value) & LOCKED_FEATURES)
        if locked:
            raise ValueError(f"These features cannot be switched off: {', '.join(locked)}")
        unknown = sorted(set(value) - SWITCHABLE_FEATURES)
        if unknown:
            raise ValueError(f"Unknown features: {', '.join(unknown)}")
        return value


def read_feature_overrides(settings_json: dict | None) -> FeatureOverrides:
    block = (settings_json or {}).get(FEATURE_OVERRIDES_KEY) or {}
    if not isinstance(block, dict):
        block = {}
    return FeatureOverrides.model_validate(block)


def write_feature_overrides(settings_json: dict | None, value: FeatureOverrides) -> dict:
    merged = dict(settings_json or {})
    merged[FEATURE_OVERRIDES_KEY] = value.model_dump()
    return merged

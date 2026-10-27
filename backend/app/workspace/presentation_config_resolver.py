"""Resolve effective presentation tier config (global env + workspace overrides)."""

from __future__ import annotations

import logging

from sqlalchemy import select

from app.ask_data.presentation_tier_config import (
    PresentationTierConfig,
    PresentationTierOverrides,
    resolve_presentation_tier_config,
)
from app.core.config import Settings
from app.db.platform_models import WorkspaceRow
from app.workspace.ask_data_settings import read_ask_data_settings

logger = logging.getLogger(__name__)


def overrides_from_workspace_settings(settings_json: dict | None) -> PresentationTierOverrides | None:
    ask = read_ask_data_settings(settings_json)
    return ask.presentation


def load_presentation_tier_config(
    settings: Settings,
    *,
    session_factory,
    workspace_id: str | None,
) -> PresentationTierConfig:
    overrides: PresentationTierOverrides | None = None
    if session_factory is not None and workspace_id:
        try:
            with session_factory() as session:
                row = session.get(WorkspaceRow, workspace_id)
                if row is not None:
                    overrides = overrides_from_workspace_settings(row.settings_json)
        except Exception:
            logger.debug("presentation_tier_config workspace load failed", exc_info=True)
    return resolve_presentation_tier_config(settings, workspace_overrides=overrides)

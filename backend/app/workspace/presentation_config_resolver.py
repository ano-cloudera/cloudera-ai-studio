"""Resolve effective presentation tier config (global env + workspace overrides)."""

from __future__ import annotations

import logging
import uuid


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
    workspace_id: str | uuid.UUID | None,
) -> PresentationTierConfig:
    overrides: PresentationTierOverrides | None = None
    if session_factory is not None and workspace_id:
        try:
            # The id arrives as text from an endpoint; the column is a UUID and a lookup by text fails, so the workspace's own
            # settings were never read and every saved choice came back as the deployment default.
            key = workspace_id if isinstance(workspace_id, uuid.UUID) else uuid.UUID(str(workspace_id))
            with session_factory() as session:
                row = session.get(WorkspaceRow, key)
                if row is not None:
                    overrides = overrides_from_workspace_settings(row.settings_json)
        except Exception:  # noqa: BLE001 - the deployment default applies, but this is worth seeing: it hides a saved choice
            logger.warning("presentation_tier_config workspace load failed workspace_id=%s", workspace_id, exc_info=True)
    return resolve_presentation_tier_config(settings, workspace_overrides=overrides)

from __future__ import annotations

from fastapi import APIRouter, Query, Request

from app.api.v1.mcp import _load_workspace, _require_platform_database_url
from app.db.platform_engine import get_session_factory
from app.workspace.feature_overrides import (
    LOCKED_FEATURES,
    SWITCHABLE_FEATURES,
    FeatureOverrides,
    read_feature_overrides,
    write_feature_overrides,
)

router = APIRouter(prefix="/features", tags=["features"])


def _payload(overrides: FeatureOverrides, workspace_slug: str) -> dict:
    return {
        "overrides": overrides.overrides,
        "switchable": sorted(SWITCHABLE_FEATURES),
        "locked": sorted(LOCKED_FEATURES),
        "workspace_slug": workspace_slug,
    }


@router.get("/overrides")
def get_feature_overrides(request: Request, workspace_slug: str = Query("default")) -> dict:
    factory = get_session_factory(_require_platform_database_url(request))
    with factory() as session:
        workspace = _load_workspace(session, workspace_slug=workspace_slug)
        return _payload(read_feature_overrides(workspace.settings_json), workspace_slug)


@router.put("/overrides")
def put_feature_overrides(body: FeatureOverrides, request: Request, workspace_slug: str = Query("default")) -> dict:
    """Replace the overrides of the workspace ({} puts every feature back to the deployment default)."""
    factory = get_session_factory(_require_platform_database_url(request))
    with factory() as session:
        workspace = _load_workspace(session, workspace_slug=workspace_slug)
        workspace.settings_json = write_feature_overrides(workspace.settings_json, body)
        session.add(workspace)
        session.commit()
        session.refresh(workspace)
        return _payload(read_feature_overrides(workspace.settings_json), workspace_slug)

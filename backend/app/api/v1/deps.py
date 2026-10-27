from __future__ import annotations

from collections.abc import Generator

from fastapi import HTTPException, Request
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.metadata_db import platform_metadata_configured
from app.db.platform_engine import get_session_factory
from app.projects.resolver import load_default_project


def require_platform_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    if not platform_metadata_configured(settings):
        raise HTTPException(
            status_code=503,
            detail="Platform metadata requires DATABASE_URL (PostgreSQL or SQLite)",
        )
    return settings


# Backward-compatible aliases (METADATA-001).
require_postgres_settings = require_platform_settings


def platform_session(request: Request) -> Generator[Session, None, None]:
    settings = require_platform_settings(request)
    factory = get_session_factory(settings.database_url)
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


postgres_session = platform_session


def default_project_context(request: Request) -> tuple:
    settings = require_platform_settings(request)
    project = load_default_project(settings)
    if not project:
        raise HTTPException(status_code=404, detail="Default project not seeded")
    return project.workspace_id, project.id

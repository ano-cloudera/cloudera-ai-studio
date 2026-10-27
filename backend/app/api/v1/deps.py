from __future__ import annotations

from collections.abc import Generator

from fastapi import HTTPException, Request
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.platform_engine import get_session_factory
from app.projects.resolver import load_default_project


def require_postgres_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    url = (settings.database_url or "").strip()
    if settings.state_store.strip().lower() != "postgres" or not url:
        raise HTTPException(
            status_code=503,
            detail="Document intelligence requires STATE_STORE=postgres and DATABASE_URL",
        )
    return settings


def postgres_session(request: Request) -> Generator[Session, None, None]:
    settings = require_postgres_settings(request)
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


def default_project_context(request: Request) -> tuple:
    settings = require_postgres_settings(request)
    project = load_default_project(settings)
    if not project:
        raise HTTPException(status_code=404, detail="Default project not seeded")
    return project.workspace_id, project.id

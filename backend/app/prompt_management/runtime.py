from __future__ import annotations

import uuid
from contextlib import contextmanager
from contextvars import Token

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.platform_engine import get_session_factory
from app.prompt_management.resolver import (
    reset_prompt_resolution_context,
    reset_resolver_session,
    set_prompt_resolution_context,
    set_resolver_session,
)


@contextmanager
def prompt_runtime(settings: Settings, workspace_id: uuid.UUID | None, project_id: uuid.UUID | None):
    ctx_token = set_prompt_resolution_context(workspace_id, project_id)
    session: Session | None = None
    sess_token: Token | None = None
    url = (settings.database_url or "").strip()
    from app.db.metadata_db import platform_metadata_configured

    if platform_metadata_configured(settings) and url:
        session = get_session_factory(url)()
        sess_token = set_resolver_session(session)
    try:
        yield
    finally:
        if sess_token is not None:
            reset_resolver_session(sess_token)
        if session is not None:
            session.close()
        reset_prompt_resolution_context(ctx_token)

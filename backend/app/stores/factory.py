from __future__ import annotations

import logging

from app.core.config import Settings
from app.projects.resolver import get_default_project_ids, load_default_project
from app.stores.postgres_conversation import PostgresConversationStore
from app.stores.postgres_usage import PostgresUsageStore
from app.stores.protocols import ConversationStoreProtocol, UsageStoreProtocol
from app.stores.sqlite_conversation import SQLiteConversationStore
from app.stores.sqlite_usage import SQLiteUsageStore

logger = logging.getLogger(__name__)


def _wants_postgres(settings: Settings) -> bool:
    return settings.state_store.strip().lower() == "postgres" and bool((settings.database_url or "").strip())


def log_active_stores(settings: Settings, conversation_store: ConversationStoreProtocol, usage_store: UsageStoreProtocol) -> None:
    logger.info(
        "state_store configured=%s conversation_adapter=%s usage_adapter=%s postgres_configured=%s",
        settings.state_store.strip().lower(),
        type(conversation_store).__name__,
        type(usage_store).__name__,
        bool((settings.database_url or "").strip()),
    )


def build_conversation_store(settings: Settings) -> ConversationStoreProtocol:
    if _wants_postgres(settings):
        try:
            project = load_default_project(settings)
            if not project:
                raise RuntimeError("default project not seeded")
            return PostgresConversationStore(
                settings.database_url,
                default_project_id=project.id,
            )
        except Exception as exc:
            logger.warning(
                "conversation_store postgres unavailable (%s) — falling back to sqlite",
                exc,
            )
    return SQLiteConversationStore(settings.conversation_db_path)


def build_usage_store(settings: Settings) -> UsageStoreProtocol:
    if _wants_postgres(settings):
        try:
            ids = get_default_project_ids(settings)
            workspace_id = project_id = None
            if ids:
                workspace_id, project_id = ids
            return PostgresUsageStore(
                settings.database_url,
                workspace_id=workspace_id,
                project_id=project_id,
            )
        except Exception as exc:
            logger.warning(
                "usage_store postgres unavailable (%s) — falling back to sqlite",
                exc,
            )
    return SQLiteUsageStore(settings.usage_db_path)


def init_postgres_platform(settings: Settings) -> None:
    """Create tables (if needed) and seed default workspace/project."""
    if not _wants_postgres(settings):
        return
    from app.db.platform_engine import get_platform_engine
    from app.db.platform_models import Base
    from app.projects.bootstrap import ensure_platform_seed

    from app.db.platform_engine import get_session_factory

    engine = get_platform_engine(settings.database_url)
    Base.metadata.create_all(engine)
    factory = get_session_factory(settings.database_url)
    with factory() as session:
        ensure_platform_seed(session, backend_root=settings.project_root.parent)

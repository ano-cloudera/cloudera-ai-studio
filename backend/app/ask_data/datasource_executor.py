from __future__ import annotations

import asyncio
import logging
import uuid
from time import perf_counter
from typing import Any

from sqlalchemy.orm import Session

from app.ask_data.types import DatasourceExecutionContext
from app.connectors.errors import ConnectorError
from app.connectors.factory import ConnectorFactory
from app.connectors.serialization import json_safe_row
from app.connectors.service import ConnectorRegistryService
from app.connectors.sql_safety import assert_connector_readonly_sql
from app.core.config import Settings
from app.db.platform_models import ProjectRow
from app.ask_data.legacy_executor import build_query_executor

logger = logging.getLogger(__name__)


class ConnectorDatasourceExecutor:
    def __init__(self, session: Session, *, settings: Settings) -> None:
        self._session = session
        self._settings = settings
        self._registry = ConnectorRegistryService(session, settings=settings)
        self._factory = ConnectorFactory(settings=settings)

    def execute_sync(
        self,
        sql: str,
        *,
        context: DatasourceExecutionContext,
        workspace_id: uuid.UUID,
        project_id: uuid.UUID,
        max_rows: int,
    ) -> dict[str, Any]:
        if context.legacy_fallback or not context.connector_id:
            raise ConnectorError("DATASOURCE_UNRESOLVED", "No connector context", 422)
        row = self._registry.get_connector(context.connector_id, workspace_id=workspace_id, project_id=project_id)
        assert_connector_readonly_sql(sql)
        adapter = self._registry.build_adapter(row)
        started = perf_counter()
        try:
            result = adapter.execute_readonly_query(sql, max_rows=max_rows)
        except ConnectorError:
            raise
        except Exception as exc:
            logger.exception("connector_query_failed connector_id=%s", context.connector_id)
            raise ConnectorError("CONNECTION_FAILED", str(exc), 502) from exc
        duration_ms = round((perf_counter() - started) * 1000, 2)
        rows = [json_safe_row(dict(r)) for r in result.rows]
        return {
            "columns": list(result.columns),
            "rows": rows,
            "row_count": result.row_count,
            "execution_ms": duration_ms,
            "connector_type": context.connector_type,
            "connector_id": str(context.connector_id),
            "connector_name": context.connector_name,
            "truncated": result.row_count >= max_rows,
        }


class RoutedQueryExecutor:
    """Per-request Ask Data execution: connector registry or legacy Impala/DuckDB."""

    def __init__(self, settings: Settings, session_factory) -> None:
        self._settings = settings
        self._session_factory = session_factory
        self._legacy = build_query_executor(settings)

    async def execute(self, sql: str, state: dict[str, Any]) -> dict[str, Any]:
        from app.ask_data.types import DatasourceExecutionContext

        raw_ctx = state.get("datasource_context")
        ctx = DatasourceExecutionContext.from_dict(raw_ctx) if isinstance(raw_ctx, dict) else None
        if ctx and not ctx.legacy_fallback and ctx.connector_id:
            workspace_id, project_id = self._project_scope(state)
            if workspace_id is None or project_id is None:
                raise ConnectorError("DATASOURCE_UNRESOLVED", "Project context unavailable", 503)
            with self._session_factory() as session:
                executor = ConnectorDatasourceExecutor(session, settings=self._settings)
                return await asyncio.to_thread(
                    executor.execute_sync,
                    sql,
                    context=ctx,
                    workspace_id=workspace_id,
                    project_id=project_id,
                    max_rows=self._settings.sql_max_rows,
                )
        return await self._legacy.execute(sql, state)

    def _project_scope(self, state: dict[str, Any]) -> tuple[uuid.UUID | None, uuid.UUID | None]:
        wid = state.get("workspace_id")
        pid = state.get("project_id")
        if wid and pid:
            try:
                return uuid.UUID(str(wid)), uuid.UUID(str(pid))
            except ValueError:
                pass
        project = self._load_project()
        if project is None:
            return None, None
        return project.workspace_id, project.id

    def _load_project(self) -> ProjectRow | None:
        from app.projects.resolver import load_default_project

        with self._session_factory() as session:
            return load_default_project(self._settings, session=session)

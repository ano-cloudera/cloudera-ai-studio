from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.connectors.discovery import MetadataDiscoveryService
from app.connectors.errors import ConnectorError
from app.connectors.metadata import ColumnInfo
from app.connectors.service import ConnectorRegistryService
from app.core.config import Settings, get_settings
from app.db.platform_models import SemanticEntityRow
from app.semantic_registry.connector_reference import validate_entity_connector
from app.semantic_registry.source_validators import ColumnInfo as ValidatorColumnInfo
from app.semantic_registry.source_validators import SourceCheckResult

logger = logging.getLogger(__name__)


@dataclass
class ResolvedSourceColumns:
    ok: bool
    skipped: bool = False
    message: str = ""
    columns: dict[str, ValidatorColumnInfo] | None = None
    normalized_by_column: dict[str, str] | None = None


class ConnectorMetadataResolver:
    """Resolve semantic entity physical sources through Connector Registry + C2 discovery."""

    def __init__(self, session: Session, *, settings: Settings | None = None) -> None:
        self._session = session
        self._settings = settings or get_settings()
        registry = ConnectorRegistryService(session, settings=self._settings)
        self._discovery = MetadataDiscoveryService(registry, settings=self._settings)
        self._registry = registry

    def load_columns_for_entity(
        self,
        entity: SemanticEntityRow,
        *,
        workspace_id: uuid.UUID,
        project_id: uuid.UUID,
    ) -> ResolvedSourceColumns:
        if not entity.connection_id:
            return ResolvedSourceColumns(ok=False, message="No connection_id")
        try:
            connector = validate_entity_connector(
                self._session,
                connection_id=entity.connection_id,
                workspace_id=workspace_id,
                project_id=project_id,
                require_enabled=False,
            )
            if not connector:
                return ResolvedSourceColumns(ok=False, message="Connector missing")
            if not connector.enabled:
                return ResolvedSourceColumns(ok=False, message="CONNECTOR_DISABLED")
            table = entity.table_name or entity.view_name or ""
            detail = self._discovery.describe_table(
                entity.connection_id,
                workspace_id=workspace_id,
                project_id=project_id,
                catalog=entity.catalog,
                schema=entity.schema,
                table=table,
            )
        except ConnectorError as exc:
            return ResolvedSourceColumns(ok=False, message=exc.message)
        except Exception as exc:
            logger.exception("connector_metadata_resolve_failed entity=%s", entity.key)
            return ResolvedSourceColumns(ok=False, message=str(exc))

        cols: dict[str, ValidatorColumnInfo] = {}
        normalized: dict[str, str] = {}
        for c in detail.columns:
            key = c.name.lower()
            cols[key] = ValidatorColumnInfo(name=c.name, data_type=c.native_type or c.data_type)
            normalized[key] = c.normalized_type or "UNKNOWN"
        return ResolvedSourceColumns(ok=True, columns=cols, normalized_by_column=normalized)

    def table_exists_for_entity(
        self,
        entity: SemanticEntityRow,
        *,
        workspace_id: uuid.UUID,
        project_id: uuid.UUID,
    ) -> SourceCheckResult:
        resolved = self.load_columns_for_entity(entity, workspace_id=workspace_id, project_id=project_id)
        if resolved.skipped:
            return SourceCheckResult(ok=False, skipped=True, message=resolved.message)
        if resolved.message == "CONNECTOR_DISABLED":
            return SourceCheckResult(ok=False, message="CONNECTOR_DISABLED")
        if not resolved.ok or not resolved.columns:
            return SourceCheckResult(ok=False, message=resolved.message or "Table not found")
        return SourceCheckResult(ok=True, columns=resolved.columns)

    def describe_table(
        self,
        connector_id: uuid.UUID,
        *,
        workspace_id: uuid.UUID,
        project_id: uuid.UUID,
        catalog: str | None,
        schema: str | None,
        table: str,
    ):
        return self._discovery.describe_table(
            connector_id,
            workspace_id=workspace_id,
            project_id=project_id,
            catalog=catalog,
            schema=schema,
            table=table,
        )

    @staticmethod
    def columns_from_detail(columns: list[ColumnInfo]) -> dict[str, ValidatorColumnInfo]:
        return {c.name.lower(): ValidatorColumnInfo(name=c.name, data_type=c.native_type or c.data_type) for c in columns}

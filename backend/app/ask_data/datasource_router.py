from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.ask_data.entity_registry import assert_version_in_project, find_entity_for_dataset
from app.ask_data.physical_identifiers import normalize_table_key, qualified_physical_name, sqlglot_dialect
from app.ask_data.types import DatasourceExecutionContext, DatasourceRoutingError
from app.connectors.service import ConnectorRegistryService
from app.core.config import Settings
from app.db.platform_models import SemanticEntityRow


class AskDataDatasourceRouter:
    def __init__(self, session: Session, *, settings: Settings) -> None:
        self._session = session
        self._settings = settings
        self._connectors = ConnectorRegistryService(session, settings=settings)

    def resolve_for_governed_metric(
        self,
        *,
        workspace_id: uuid.UUID,
        project_id: uuid.UUID,
        semantic_version_id: uuid.UUID | None,
        dataset_name: str,
        bundle_mode: str,
    ) -> DatasourceExecutionContext | DatasourceRoutingError:
        if not semantic_version_id or bundle_mode == "legacy":
            return DatasourceExecutionContext(
                legacy_fallback=True,
                dialect=sqlglot_dialect(None, legacy_data_backend=self._settings.data_backend),
            )
        try:
            assert_version_in_project(
                self._session,
                semantic_version_id=semantic_version_id,
                workspace_id=workspace_id,
                project_id=project_id,
            )
        except ValueError as exc:
            return DatasourceRoutingError(
                code="DATASOURCE_UNRESOLVED",
                message=str(exc),
                safe_message="Semantic runtime version could not be validated for this project.",
            )

        entity = find_entity_for_dataset(
            self._session,
            semantic_version_id=semantic_version_id,
            dataset_name=dataset_name,
        )
        if entity is None or entity.connection_id is None:
            return DatasourceExecutionContext(
                legacy_fallback=True,
                semantic_version_id=semantic_version_id,
                dialect=sqlglot_dialect(None, legacy_data_backend=self._settings.data_backend),
            )

        return self._connector_context(
            entity,
            dataset_name=dataset_name,
            workspace_id=workspace_id,
            project_id=project_id,
            semantic_version_id=semantic_version_id,
        )

    def resolve_entities(
        self,
        *,
        workspace_id: uuid.UUID,
        project_id: uuid.UUID,
        semantic_version_id: uuid.UUID | None,
        dataset_names: list[str],
        bundle_mode: str,
    ) -> DatasourceExecutionContext | DatasourceRoutingError:
        if not semantic_version_id or bundle_mode == "legacy":
            return DatasourceExecutionContext(
                legacy_fallback=True,
                dialect=sqlglot_dialect(None, legacy_data_backend=self._settings.data_backend),
            )
        entities: list[SemanticEntityRow] = []
        for ds in dataset_names:
            ent = find_entity_for_dataset(
                self._session,
                semantic_version_id=semantic_version_id,
                dataset_name=ds,
            )
            if ent:
                entities.append(ent)

        if not entities:
            return DatasourceExecutionContext(
                legacy_fallback=True,
                semantic_version_id=semantic_version_id,
                dialect=sqlglot_dialect(None, legacy_data_backend=self._settings.data_backend),
            )

        connection_ids = {e.connection_id for e in entities}
        has_connector = any(cid is not None for cid in connection_ids)
        has_legacy = any(cid is None for cid in connection_ids)
        if has_connector and has_legacy:
            return DatasourceRoutingError(
                code="MIXED_LEGACY_CONNECTOR",
                message="Query mixes legacy and connector-linked semantic entities",
                safe_message="This question mixes legacy and connector-backed datasets, which is not supported.",
            )

        connector_ids = {cid for cid in connection_ids if cid is not None}
        if len(connector_ids) > 1:
            return DatasourceRoutingError(
                code="CROSS_CONNECTOR_QUERY_UNSUPPORTED",
                message="Entities reference multiple connectors",
                safe_message="This question spans multiple data sources, which is not supported yet.",
            )

        linked = [e for e in entities if e.connection_id]
        if not linked:
            return DatasourceExecutionContext(
                legacy_fallback=True,
                semantic_version_id=semantic_version_id,
                dialect=sqlglot_dialect(None, legacy_data_backend=self._settings.data_backend),
            )

        primary = linked[0]
        ctx = self._connector_context(
            primary,
            dataset_name=dataset_names[0] if dataset_names else primary.key,
            workspace_id=workspace_id,
            project_id=project_id,
            semantic_version_id=semantic_version_id,
        )
        if isinstance(ctx, DatasourceRoutingError):
            return ctx

        qualified: dict[str, str] = {}
        allowed: set[str] = set()
        keys: list[str] = []
        for ent in linked:
            keys.append(ent.key)
            q = qualified_physical_name(
                connector_type=str(ctx.connector_type),
                catalog=ent.catalog,
                schema=ent.schema,
                table_name=ent.table_name,
                view_name=ent.view_name,
            )
            for ds in dataset_names:
                if ent.key == ds or ent.name == ds:
                    qualified[ds] = q
            allowed.add(normalize_table_key(q))

        return DatasourceExecutionContext(
            legacy_fallback=False,
            connector_id=ctx.connector_id,
            connector_type=ctx.connector_type,
            connector_name=ctx.connector_name,
            dialect=ctx.dialect,
            semantic_version_id=semantic_version_id,
            semantic_entity_keys=tuple(keys),
            qualified_sources=qualified or ctx.qualified_sources,
            allowed_physical_tables=frozenset(allowed or ctx.allowed_physical_tables),
        )

    def resolve_raw_table(
        self,
        *,
        workspace_id: uuid.UUID,
        project_id: uuid.UUID,
        connector_id: uuid.UUID,
        catalog: str | None,
        schema: str | None,
        table: str,
    ) -> DatasourceExecutionContext | DatasourceRoutingError:
        try:
            row = self._connectors.get_connector(connector_id, workspace_id=workspace_id, project_id=project_id)
        except Exception:
            return DatasourceRoutingError(
                code="CONNECTOR_NOT_FOUND",
                message="Connector not found for table context",
                safe_message="The datasource connection for this table is not available.",
            )
        if not row.enabled:
            return DatasourceRoutingError(
                code="CONNECTOR_DISABLED",
                message=f"Connector {row.name} is disabled",
                safe_message="The datasource connection for this table is currently disabled.",
            )
        try:
            qualified = qualified_physical_name(
                connector_type=row.connector_type,
                catalog=catalog,
                schema=schema,
                table_name=table,
                view_name=None,
            )
        except ValueError as exc:
            return DatasourceRoutingError(
                code="DATASOURCE_UNRESOLVED",
                message=str(exc),
                safe_message="Physical table identity for this table is incomplete.",
            )
        key = normalize_table_key(qualified)
        return DatasourceExecutionContext(
            legacy_fallback=False,
            connector_id=row.id,
            connector_type=row.connector_type,
            connector_name=row.name,
            dialect=sqlglot_dialect(row.connector_type),
            semantic_version_id=None,
            semantic_entity_keys=(),
            qualified_sources={"raw": qualified},
            allowed_physical_tables=frozenset({key}),
        )

    def _connector_context(
        self,
        entity: SemanticEntityRow,
        *,
        dataset_name: str,
        workspace_id: uuid.UUID,
        project_id: uuid.UUID,
        semantic_version_id: uuid.UUID,
    ) -> DatasourceExecutionContext | DatasourceRoutingError:
        assert entity.connection_id is not None
        try:
            row = self._connectors.get_connector(entity.connection_id, workspace_id=workspace_id, project_id=project_id)
        except Exception:
            return DatasourceRoutingError(
                code="CONNECTOR_NOT_FOUND",
                message="Connector not found for semantic entity",
                safe_message="The datasource connection for this metric is not available.",
            )
        if not row.enabled:
            return DatasourceRoutingError(
                code="CONNECTOR_DISABLED",
                message=f"Connector {row.name} is disabled",
                safe_message="The datasource connection for this metric is currently disabled.",
            )
        try:
            qualified = qualified_physical_name(
                connector_type=row.connector_type,
                catalog=entity.catalog,
                schema=entity.schema,
                table_name=entity.table_name,
                view_name=entity.view_name,
            )
        except ValueError as exc:
            return DatasourceRoutingError(
                code="DATASOURCE_UNRESOLVED",
                message=str(exc),
                safe_message="Physical table mapping for this metric is incomplete.",
            )
        return DatasourceExecutionContext(
            legacy_fallback=False,
            connector_id=row.id,
            connector_type=row.connector_type,
            connector_name=row.name,
            dialect=sqlglot_dialect(row.connector_type),
            semantic_version_id=semantic_version_id,
            semantic_entity_keys=(entity.key,),
            qualified_sources={dataset_name: qualified},
            allowed_physical_tables=frozenset({normalize_table_key(qualified)}),
        )

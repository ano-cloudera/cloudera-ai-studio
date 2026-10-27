from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.connectors.errors import ConnectorError
from app.core.config import Settings, get_settings
from app.db.platform_models import SemanticEntityRow, SemanticVersionRow
from app.semantic_registry.connector_reference import connector_source_type, validate_entity_connector
from app.semantic_registry.connector_resolver import ConnectorMetadataResolver
from app.semantic_registry.dimension_candidates import column_to_dimension_key, suggest_dimension_candidates
from app.services.semantic_registry_service import SemanticRegistryError, SemanticRegistryService


@dataclass
class EntityImportResult:
    entity: SemanticEntityRow
    dimensions_created: int = 0
    columns_discovered: int = 0
    warnings: list[str] = field(default_factory=list)


class SemanticEntityImportService:
    def __init__(self, session: Session, *, settings: Settings | None = None) -> None:
        self._session = session
        self._settings = settings or get_settings()
        self._semantic = SemanticRegistryService(session)
        self._resolver = ConnectorMetadataResolver(session, settings=self._settings)

    def import_preview(
        self,
        version_id: uuid.UUID,
        *,
        workspace_id: uuid.UUID,
        project_id: uuid.UUID,
        connector_id: uuid.UUID,
        catalog: str | None,
        schema: str | None,
        table: str,
    ) -> dict:
        self._semantic.ensure_draft_version(version_id, workspace_id=workspace_id, project_id=project_id)
        validate_entity_connector(
            self._session,
            connection_id=connector_id,
            workspace_id=workspace_id,
            project_id=project_id,
            require_enabled=True,
        )
        detail = self._resolver.describe_table(
            connector_id,
            workspace_id=workspace_id,
            project_id=project_id,
            catalog=catalog,
            schema=schema,
            table=table,
        )
        candidates = suggest_dimension_candidates(detail.columns)
        existing = self._find_duplicate(
            version_id,
            connection_id=connector_id,
            catalog=catalog,
            schema=schema,
            table=table,
            table_type=detail.table_type,
        )
        return {
            "table_type": detail.table_type,
            "columns": [
                {
                    "name": c.name,
                    "native_type": c.native_type or c.data_type,
                    "normalized_type": c.normalized_type,
                    "nullable": c.nullable,
                    "comment": c.comment,
                }
                for c in detail.columns
            ],
            "candidate_dimensions": [
                {
                    "column": c.name,
                    "suggested_key": column_to_dimension_key(c.name),
                    "normalized_type": c.normalized_type,
                }
                for c in candidates
            ],
            "existing_entity": (
                {"id": str(existing.id), "key": existing.key, "name": existing.name} if existing else None
            ),
            "primary_key": detail.primary_key,
        }

    def import_entity(
        self,
        version_id: uuid.UUID,
        *,
        workspace_id: uuid.UUID,
        project_id: uuid.UUID,
        connector_id: uuid.UUID,
        catalog: str | None,
        schema: str | None,
        table: str,
        name: str,
        key: str,
        description: str | None = None,
        dimension_columns: list[str] | None = None,
    ) -> EntityImportResult:
        self._semantic.ensure_draft_version(version_id, workspace_id=workspace_id, project_id=project_id)
        connector = validate_entity_connector(
            self._session,
            connection_id=connector_id,
            workspace_id=workspace_id,
            project_id=project_id,
            require_enabled=True,
        )
        if not connector:
            raise SemanticRegistryError("connector_not_found", "Connector not found", 404)

        try:
            detail = self._resolver.describe_table(
                connector_id,
                workspace_id=workspace_id,
                project_id=project_id,
                catalog=catalog,
                schema=schema,
                table=table,
            )
        except ConnectorError as exc:
            raise SemanticRegistryError(exc.code, exc.message, exc.status_code) from exc

        warnings: list[str] = []
        duplicate = self._find_duplicate(
            version_id,
            connection_id=connector_id,
            catalog=catalog,
            schema=schema,
            table=table,
            table_type=detail.table_type,
        )
        if duplicate:
            raise SemanticRegistryError(
                "duplicate_entity_source",
                "This draft already contains an entity mapped to the same connector table",
                409,
            )

        is_view = detail.table_type.upper() == "VIEW"
        fingerprint = hashlib.sha256(
            "|".join(f"{c.name}:{c.normalized_type}" for c in detail.columns).encode()
        ).hexdigest()[:16]
        metadata = {
            "last_discovered_at": datetime.now(timezone.utc).isoformat(),
            "column_count": len(detail.columns),
            "source_fingerprint": fingerprint,
            "connector_name": connector.name,
            "physical_columns": [
                {
                    "name": c.name,
                    "normalized_type": c.normalized_type or c.data_type,
                }
                for c in detail.columns
            ],
        }
        pk = ",".join(detail.primary_key) if detail.primary_key else None
        if not pk:
            warnings.append("No primary key detected.")

        entity = self._semantic.create_entity(
            version_id,
            workspace_id=workspace_id,
            project_id=project_id,
            data={
                "key": key.strip(),
                "name": name.strip(),
                "description": description,
                "source_type": connector_source_type(connector.connector_type),
                "catalog": catalog or detail.catalog,
                "db_schema": schema or detail.schema,
                "table_name": None if is_view else table,
                "view_name": table if is_view else None,
                "primary_key": pk,
                "connection_id": str(connector_id),
                "metadata": metadata,
            },
        )

        dims_created = 0
        if dimension_columns:
            col_map = {c.name.lower(): c for c in detail.columns}
            for col_name in dimension_columns:
                col = col_map.get(col_name.lower())
                if not col:
                    warnings.append(f"Column not found for dimension: {col_name}")
                    continue
                dim_key = column_to_dimension_key(col.name)
                self._semantic.create_dimension(
                    version_id,
                    workspace_id=workspace_id,
                    project_id=project_id,
                    data={
                        "key": dim_key,
                        "name": col.name.replace("_", " ").title(),
                        "source_entity_key": entity.key,
                        "source_column": col.name,
                        "data_type": col.normalized_type or col.data_type,
                        "metadata": {"normalized_type": col.normalized_type},
                    },
                )
                dims_created += 1

        return EntityImportResult(
            entity=entity,
            dimensions_created=dims_created,
            columns_discovered=len(detail.columns),
            warnings=warnings,
        )

    def _find_duplicate(
        self,
        version_id: uuid.UUID,
        *,
        connection_id: uuid.UUID,
        catalog: str | None,
        schema: str | None,
        table: str,
        table_type: str,
    ) -> SemanticEntityRow | None:
        is_view = table_type.upper() == "VIEW"
        q = select(SemanticEntityRow).where(
            SemanticEntityRow.semantic_version_id == version_id,
            SemanticEntityRow.connection_id == connection_id,
        )
        if catalog:
            q = q.where(SemanticEntityRow.catalog == catalog)
        if schema:
            q = q.where(SemanticEntityRow.schema == schema)
        if is_view:
            q = q.where(SemanticEntityRow.view_name == table)
        else:
            q = q.where(SemanticEntityRow.table_name == table)
        return self._session.execute(q).scalar_one_or_none()

    @staticmethod
    def version_project_context(session: Session, version_id: uuid.UUID) -> tuple[uuid.UUID, uuid.UUID]:
        from app.db.platform_models import SemanticModelRow

        version = session.get(SemanticVersionRow, version_id)
        if not version:
            raise SemanticRegistryError("not_found", "Semantic version not found", 404)
        model = session.get(SemanticModelRow, version.semantic_model_id)
        if not model:
            raise SemanticRegistryError("not_found", "Semantic model not found", 404)
        return model.workspace_id, model.project_id

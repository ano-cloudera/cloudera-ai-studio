from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.platform_models import (
    ConnectorRow,
    SemanticEntityRow,
    SemanticModelRow,
    SemanticRuntimeDeploymentRow,
    SemanticRuntimeStateRow,
    SemanticVersionRow,
)
from app.semantic_registry.registry_errors import SemanticRegistryError

_CONNECTOR_SOURCE_TYPES = {"impala", "trino", "postgres"}


def connector_source_type(connector_type: str) -> str:
    if connector_type not in _CONNECTOR_SOURCE_TYPES:
        raise SemanticRegistryError("invalid_connector_type", f"Unsupported connector type: {connector_type}", 422)
    return connector_type


def validate_entity_connector(
    session: Session,
    *,
    connection_id: uuid.UUID | None,
    workspace_id: uuid.UUID,
    project_id: uuid.UUID,
    source_type: str | None = None,
    require_enabled: bool = False,
) -> ConnectorRow | None:
    if connection_id is None:
        return None
    row = session.get(ConnectorRow, connection_id)
    if not row:
        raise SemanticRegistryError("connector_not_found", "Connector not found", 404)
    if row.workspace_id != workspace_id or row.project_id != project_id:
        raise SemanticRegistryError("connector_scope_mismatch", "Connector belongs to another project", 403)
    if require_enabled and not row.enabled:
        raise SemanticRegistryError("CONNECTOR_DISABLED", "Connector is disabled", 409)
    expected = connector_source_type(row.connector_type)
    if source_type and source_type not in {"logical", expected}:
        raise SemanticRegistryError(
            "source_type_mismatch",
            f"Entity source_type must align with connector type ({expected})",
            422,
        )
    return row


def count_semantic_references(session: Session, connector_id: uuid.UUID) -> int:
    return int(
        session.execute(
            select(func.count()).select_from(SemanticEntityRow).where(SemanticEntityRow.connection_id == connector_id)
        ).scalar_one()
    )


def semantic_reference_summary(session: Session, connector_id: uuid.UUID) -> dict:
    rows = session.execute(
        select(
            SemanticEntityRow.id.label("entity_id"),
            SemanticEntityRow.key.label("entity_key"),
            SemanticEntityRow.name.label("entity_name"),
            SemanticModelRow.key.label("semantic_model_key"),
            SemanticModelRow.name.label("semantic_model_name"),
        )
        .join(SemanticVersionRow, SemanticVersionRow.id == SemanticEntityRow.semantic_version_id)
        .join(SemanticModelRow, SemanticModelRow.id == SemanticVersionRow.semantic_model_id)
        .where(SemanticEntityRow.connection_id == connector_id)
        .order_by(SemanticModelRow.key, SemanticEntityRow.key)
        .limit(100)
    ).mappings()
    entities = [
        {
            "entity_id": str(r["entity_id"]),
            "entity_key": r["entity_key"],
            "entity_name": r["entity_name"],
            "semantic_model_key": r["semantic_model_key"],
            "semantic_model_name": r["semantic_model_name"],
        }
        for r in rows
    ]
    return {"count": count_semantic_references(session, connector_id), "entities": entities}


def connector_used_by_runtime_active_deployment(
    session: Session,
    *,
    project_id: uuid.UUID,
    connector_id: uuid.UUID,
) -> bool:
    """True if any entity on the runtime-active semantic version references the connector."""
    dep_ids = session.execute(
        select(SemanticRuntimeDeploymentRow.semantic_version_id)
        .join(SemanticRuntimeStateRow, SemanticRuntimeStateRow.active_deployment_id == SemanticRuntimeDeploymentRow.id)
        .join(SemanticModelRow, SemanticModelRow.id == SemanticRuntimeStateRow.semantic_model_id)
        .where(SemanticModelRow.project_id == project_id)
    ).scalars()
    version_ids = [vid for vid in dep_ids if vid]
    if not version_ids:
        return False
    hit = session.execute(
        select(func.count())
        .select_from(SemanticEntityRow)
        .where(
            SemanticEntityRow.connection_id == connector_id,
            SemanticEntityRow.semantic_version_id.in_(version_ids),
        )
    ).scalar_one()
    return int(hit) > 0

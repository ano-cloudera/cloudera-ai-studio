from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.connectors.config import parse_connector_config
from app.connectors.errors import ConnectorError
from app.connectors.factory import ConnectorFactory
from app.connectors.secrets import EnvironmentSecretProvider, mask_secret_ref
from app.core.config import Settings, get_settings
from app.db.platform_models import ConnectorRow, ProjectRow

logger = logging.getLogger(__name__)


class ConnectorRegistryService:
    def __init__(self, session: Session, settings: Settings | None = None) -> None:
        self._session = session
        self._settings = settings or get_settings()
        self._factory = ConnectorFactory(self._settings, EnvironmentSecretProvider())
        self._secrets = EnvironmentSecretProvider()

    def list_connectors(
        self,
        *,
        workspace_id: uuid.UUID,
        project_id: uuid.UUID,
        connector_type: str | None = None,
        enabled: bool | None = None,
    ) -> list[ConnectorRow]:
        stmt = select(ConnectorRow).where(
            ConnectorRow.workspace_id == workspace_id,
            ConnectorRow.project_id == project_id,
        )
        if connector_type:
            stmt = stmt.where(ConnectorRow.connector_type == connector_type)
        if enabled is not None:
            stmt = stmt.where(ConnectorRow.enabled == enabled)
        return list(self._session.execute(stmt.order_by(ConnectorRow.name)).scalars().all())

    def get_connector(
        self,
        connector_id: uuid.UUID,
        *,
        workspace_id: uuid.UUID,
        project_id: uuid.UUID,
    ) -> ConnectorRow:
        row = self._session.get(ConnectorRow, connector_id)
        if not row or row.workspace_id != workspace_id or row.project_id != project_id:
            raise ConnectorError("CONNECTOR_NOT_FOUND", "Connector not found", 404)
        return row

    def create_connector(
        self,
        *,
        workspace_id: uuid.UUID,
        project_id: uuid.UUID,
        name: str,
        key: str,
        connector_type: str,
        config: dict[str, Any],
        description: str | None = None,
        secret_ref: str | None = None,
        enabled: bool = True,
        created_by: str | None = None,
        metadata: dict | None = None,
    ) -> ConnectorRow:
        if connector_type not in {"impala", "trino", "postgres"}:
            raise ConnectorError("INVALID_CONFIG", f"Unsupported connector type: {connector_type}", 422)
        parse_connector_config(connector_type, config)
        self._assert_unique_key(workspace_id, project_id, key)
        row = ConnectorRow(
            workspace_id=workspace_id,
            project_id=project_id,
            name=name,
            key=key,
            description=description,
            connector_type=connector_type,
            status="ACTIVE",
            enabled=enabled,
            config=config,
            secret_ref=secret_ref,
            created_by=created_by,
            metadata_=metadata or {},
            last_test_status="NOT_TESTED",
        )
        self._session.add(row)
        self._session.flush()
        return row

    def update_connector(
        self,
        connector_id: uuid.UUID,
        *,
        workspace_id: uuid.UUID,
        project_id: uuid.UUID,
        patch: dict[str, Any],
    ) -> ConnectorRow:
        row = self.get_connector(connector_id, workspace_id=workspace_id, project_id=project_id)
        if "name" in patch and patch["name"]:
            row.name = patch["name"]
        if "description" in patch:
            row.description = patch["description"]
        if "enabled" in patch and patch["enabled"] is not None:
            disabling = patch["enabled"] is False and row.enabled
            if disabling:
                from app.semantic_registry.connector_reference import connector_used_by_runtime_active_deployment

                if connector_used_by_runtime_active_deployment(
                    self._session,
                    project_id=project_id,
                    connector_id=connector_id,
                ):
                    raise ConnectorError(
                        "CONNECTOR_ACTIVE_RUNTIME_DEPENDENCY",
                        "Connector is referenced by the active Ask Data semantic runtime",
                        409,
                    )
            row.enabled = bool(patch["enabled"])
            row.status = "INACTIVE" if not row.enabled else "ACTIVE"
        if "config" in patch and patch["config"] is not None:
            parse_connector_config(row.connector_type, patch["config"])
            row.config = patch["config"]
        if "secret_ref" in patch:
            row.secret_ref = patch["secret_ref"]
        if "metadata" in patch and patch["metadata"] is not None:
            row.metadata_ = patch["metadata"]
        row.updated_at = datetime.now(timezone.utc)
        self._session.flush()
        return row

    def delete_connector(
        self,
        connector_id: uuid.UUID,
        *,
        workspace_id: uuid.UUID,
        project_id: uuid.UUID,
    ) -> None:
        row = self.get_connector(connector_id, workspace_id=workspace_id, project_id=project_id)
        ref = self._session.execute(
            select(ProjectRow).where(
                ProjectRow.id == project_id,
                ProjectRow.default_connector_id == connector_id,
            )
        ).scalar_one_or_none()
        if ref:
            raise ConnectorError("CONNECTOR_IN_USE", "Connector is referenced as project default_connector_id", 409)
        from app.semantic_registry.connector_reference import count_semantic_references, semantic_reference_summary

        sem_count = count_semantic_references(self._session, connector_id)
        if sem_count:
            summary = semantic_reference_summary(self._session, connector_id)
            raise ConnectorError(
                "CONNECTOR_IN_USE",
                f"Connector is referenced by {sem_count} semantic entit{'y' if sem_count == 1 else 'ies'}",
                409,
            )
        self._session.delete(row)

    def test_connector(
        self,
        connector_id: uuid.UUID,
        *,
        workspace_id: uuid.UUID,
        project_id: uuid.UUID,
    ) -> dict:
        row = self.get_connector(connector_id, workspace_id=workspace_id, project_id=project_id)
        if not row.enabled:
            raise ConnectorError("CONNECTOR_DISABLED", "Connector is disabled", 409)
        adapter = self._factory.create(row.connector_type, dict(row.config or {}), secret_ref=row.secret_ref)
        logger.info(
            "connector_test_start connector_id=%s type=%s",
            connector_id,
            row.connector_type,
        )
        result = adapter.test_connection()
        row.last_tested_at = datetime.now(timezone.utc)
        row.last_test_status = result.status
        row.last_test_message = result.message[:2000]
        if result.status == "SUCCESS":
            row.status = "ACTIVE"
        else:
            row.status = "ERROR"
        self._session.flush()
        logger.info(
            "connector_test_done connector_id=%s status=%s latency_ms=%s",
            connector_id,
            result.status,
            result.latency_ms,
        )
        return {
            "status": result.status,
            "latency_ms": result.latency_ms,
            "server_version": result.server_version,
            "server_name": result.server_name,
            "default_catalog": result.default_catalog,
            "default_schema": result.default_schema,
            "message": result.message,
            "error_code": result.error_code,
            "phases": result.phases,
            "capabilities": result.capabilities or adapter.get_capabilities().to_api_dict(),
        }

    def get_capabilities(
        self,
        connector_id: uuid.UUID,
        *,
        workspace_id: uuid.UUID,
        project_id: uuid.UUID,
    ) -> dict:
        row = self.get_connector(connector_id, workspace_id=workspace_id, project_id=project_id)
        adapter = self._factory.create(row.connector_type, dict(row.config or {}), secret_ref=row.secret_ref)
        return adapter.get_capabilities().to_api_dict()

    def build_adapter(self, row: ConnectorRow) -> Any:
        if not row.enabled:
            raise ConnectorError("CONNECTOR_DISABLED", "Connector is disabled", 409)
        return self._factory.create(row.connector_type, dict(row.config or {}), secret_ref=row.secret_ref)

    def connector_dict(self, row: ConnectorRow) -> dict:
        return {
            "id": str(row.id),
            "workspace_id": str(row.workspace_id),
            "project_id": str(row.project_id) if row.project_id else None,
            "name": row.name,
            "key": row.key,
            "description": row.description,
            "connector_type": row.connector_type,
            "status": row.status,
            "enabled": row.enabled,
            "config": dict(row.config or {}),
            "secret_ref": mask_secret_ref(row.secret_ref),
            "credentials_configured": self._secrets.has_secret(row.secret_ref),
            "last_tested_at": row.last_tested_at,
            "last_test_status": row.last_test_status,
            "last_test_message": row.last_test_message,
            "metadata": dict(row.metadata_ or {}),
            "created_at": row.created_at,
            "updated_at": row.updated_at,
            "created_by": row.created_by,
        }

    def _assert_unique_key(self, workspace_id: uuid.UUID, project_id: uuid.UUID, key: str) -> None:
        existing = self._session.execute(
            select(ConnectorRow).where(
                ConnectorRow.workspace_id == workspace_id,
                ConnectorRow.project_id == project_id,
                ConnectorRow.key == key,
            )
        ).scalar_one_or_none()
        if existing:
            raise ConnectorError("DUPLICATE_KEY", f"Connector key already exists: {key}", 409)

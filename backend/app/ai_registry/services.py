from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.ai_registry.adapters.factory import ProviderAdapterFactory
from app.ai_registry.errors import AiRegistryError
from app.ai_registry.secrets import SecretResolver, mask_secret_ref
from app.ai_registry.types import CAPABILITIES
from app.ai_registry.validation import (
    validate_assignment,
    validate_model_key,
    validate_model_payload,
    validate_provider_key,
    validate_provider_payload,
)
from app.db.platform_models import AiModelRow, AiProviderRow, ModelAssignmentRow, ModelTestRunRow

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class _ScopeMixin:
    _session: Session

    def _provider_scope_filter(self, workspace_id: uuid.UUID, project_id: uuid.UUID):
        return (
            AiProviderRow.workspace_id == workspace_id,
            or_(AiProviderRow.project_id == project_id, AiProviderRow.project_id.is_(None)),
        )

    def _assert_provider_in_scope(self, row: AiProviderRow, *, workspace_id: uuid.UUID, project_id: uuid.UUID) -> None:
        if row.workspace_id != workspace_id:
            raise AiRegistryError("PROVIDER_NOT_FOUND", "Provider not found", 404)
        if row.project_id is not None and row.project_id != project_id:
            raise AiRegistryError("PROVIDER_NOT_FOUND", "Provider not found", 404)

    def _assert_model_in_scope(self, row: AiModelRow, *, workspace_id: uuid.UUID, project_id: uuid.UUID) -> None:
        if row.workspace_id != workspace_id:
            raise AiRegistryError("MODEL_NOT_FOUND", "Model not found", 404)
        if row.project_id is not None and row.project_id != project_id:
            raise AiRegistryError("MODEL_NOT_FOUND", "Model not found", 404)


class ProviderRegistryService(_ScopeMixin):
    def __init__(self, session: Session, secrets: SecretResolver | None = None) -> None:
        self._session = session
        self._secrets = secrets or SecretResolver()

    def list_providers(
        self,
        *,
        workspace_id: uuid.UUID,
        project_id: uuid.UUID,
        provider_type: str | None = None,
        enabled: bool | None = None,
    ) -> list[AiProviderRow]:
        stmt = select(AiProviderRow).where(*self._provider_scope_filter(workspace_id, project_id))
        if provider_type:
            stmt = stmt.where(AiProviderRow.provider_type == provider_type.upper())
        if enabled is not None:
            stmt = stmt.where(AiProviderRow.enabled == enabled)
        return list(self._session.execute(stmt.order_by(AiProviderRow.name)).scalars().all())

    def get_provider(
        self,
        provider_id: uuid.UUID,
        *,
        workspace_id: uuid.UUID,
        project_id: uuid.UUID,
    ) -> AiProviderRow:
        row = self._session.get(AiProviderRow, provider_id)
        if not row:
            raise AiRegistryError("PROVIDER_NOT_FOUND", "Provider not found", 404)
        self._assert_provider_in_scope(row, workspace_id=workspace_id, project_id=project_id)
        return row

    def create_provider(
        self,
        *,
        workspace_id: uuid.UUID,
        project_id: uuid.UUID,
        name: str,
        key: str,
        provider_type: str,
        base_url: str | None = None,
        secret_ref: str | None = None,
        enabled: bool = True,
        config_json: dict | None = None,
    ) -> AiProviderRow:
        validate_provider_key(key)
        validate_provider_payload(
            provider_type=provider_type,
            secret_ref=secret_ref,
            base_url=base_url,
            secrets=self._secrets,
        )
        self._assert_unique_provider_key(workspace_id, project_id, key)
        row = AiProviderRow(
            workspace_id=workspace_id,
            project_id=project_id,
            name=name,
            key=key,
            provider_type=provider_type.upper(),
            base_url=base_url,
            secret_ref=secret_ref,
            enabled=enabled,
            config_json=config_json or {},
            last_test_status="NOT_TESTED",
        )
        self._session.add(row)
        self._session.flush()
        return row

    def update_provider(
        self,
        provider_id: uuid.UUID,
        *,
        workspace_id: uuid.UUID,
        project_id: uuid.UUID,
        patch: dict[str, Any],
    ) -> AiProviderRow:
        row = self.get_provider(provider_id, workspace_id=workspace_id, project_id=project_id)
        merged_type = patch.get("provider_type", row.provider_type)
        merged_secret = patch["secret_ref"] if "secret_ref" in patch else row.secret_ref
        merged_base = patch.get("base_url", row.base_url)
        if any(k in patch for k in ("provider_type", "secret_ref", "base_url")):
            validate_provider_payload(
                provider_type=merged_type,
                secret_ref=merged_secret,
                base_url=merged_base,
                secrets=self._secrets,
            )
        if "name" in patch and patch["name"]:
            row.name = patch["name"]
        if "provider_type" in patch and patch["provider_type"]:
            row.provider_type = patch["provider_type"].upper()
        if "base_url" in patch:
            row.base_url = patch["base_url"]
        if "secret_ref" in patch:
            row.secret_ref = patch["secret_ref"]
        if "enabled" in patch and patch["enabled"] is not None:
            row.enabled = bool(patch["enabled"])
        if "config_json" in patch and patch["config_json"] is not None:
            row.config_json = patch["config_json"]
        row.updated_at = _utcnow()
        self._session.flush()
        return row

    def delete_provider(
        self,
        provider_id: uuid.UUID,
        *,
        workspace_id: uuid.UUID,
        project_id: uuid.UUID,
    ) -> None:
        row = self.get_provider(provider_id, workspace_id=workspace_id, project_id=project_id)
        model_count = self._session.execute(
            select(AiModelRow.id).where(AiModelRow.provider_id == provider_id).limit(1)
        ).first()
        if model_count:
            raise AiRegistryError("PROVIDER_IN_USE", "Provider has registered models", 409)
        self._session.delete(row)

    def provider_dict(self, row: AiProviderRow) -> dict[str, Any]:
        status = "DISABLED" if not row.enabled else (row.last_test_status or "NOT_TESTED")
        return {
            "id": str(row.id),
            "workspace_id": str(row.workspace_id),
            "project_id": str(row.project_id) if row.project_id else None,
            "name": row.name,
            "key": row.key,
            "provider_type": row.provider_type,
            "base_url": row.base_url,
            "secret_ref": mask_secret_ref(row.secret_ref),
            "secret_configured": self._secrets.has_secret(row.secret_ref),
            "enabled": row.enabled,
            "status": status,
            "config_json": dict(row.config_json or {}),
            "last_test_at": row.last_test_at,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }

    def _assert_unique_provider_key(self, workspace_id: uuid.UUID, project_id: uuid.UUID, key: str) -> None:
        existing = self._session.execute(
            select(AiProviderRow).where(
                AiProviderRow.workspace_id == workspace_id,
                AiProviderRow.project_id == project_id,
                AiProviderRow.key == key,
            )
        ).scalar_one_or_none()
        if existing:
            raise AiRegistryError("MODEL_INVALID", f"Provider key already exists: {key}", 409)


class ModelRegistryService(_ScopeMixin):
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_models(
        self,
        *,
        workspace_id: uuid.UUID,
        project_id: uuid.UUID,
        provider_id: uuid.UUID | None = None,
        model_type: str | None = None,
        enabled: bool | None = None,
    ) -> list[AiModelRow]:
        stmt = select(AiModelRow).where(
            AiModelRow.workspace_id == workspace_id,
            or_(AiModelRow.project_id == project_id, AiModelRow.project_id.is_(None)),
        )
        if provider_id:
            stmt = stmt.where(AiModelRow.provider_id == provider_id)
        if model_type:
            stmt = stmt.where(AiModelRow.model_type == model_type.upper())
        if enabled is not None:
            stmt = stmt.where(AiModelRow.enabled == enabled)
        return list(self._session.execute(stmt.order_by(AiModelRow.name)).scalars().all())

    def get_model(
        self,
        model_id: uuid.UUID,
        *,
        workspace_id: uuid.UUID,
        project_id: uuid.UUID,
    ) -> AiModelRow:
        row = self._session.get(AiModelRow, model_id)
        if not row:
            raise AiRegistryError("MODEL_NOT_FOUND", "Model not found", 404)
        self._assert_model_in_scope(row, workspace_id=workspace_id, project_id=project_id)
        return row

    def create_model(
        self,
        *,
        workspace_id: uuid.UUID,
        project_id: uuid.UUID,
        provider_id: uuid.UUID,
        name: str,
        key: str,
        model_id: str,
        model_type: str,
        enabled: bool = True,
        context_window: int | None = None,
        max_output_tokens: int | None = None,
        supports_streaming: bool | None = None,
        supports_tools: bool | None = None,
        supports_json_mode: bool | None = None,
        supports_vision: bool | None = None,
        config_json: dict | None = None,
    ) -> AiModelRow:
        validate_model_key(key)
        validate_model_payload(
            model_type=model_type,
            model_id=model_id,
            context_window=context_window,
            max_output_tokens=max_output_tokens,
        )
        provider = self._session.get(AiProviderRow, provider_id)
        if not provider:
            raise AiRegistryError("PROVIDER_NOT_FOUND", "Provider not found", 404)
        ProviderRegistryService(self._session)._assert_provider_in_scope(
            provider, workspace_id=workspace_id, project_id=project_id
        )
        self._assert_unique_model_key(workspace_id, project_id, key)
        row = AiModelRow(
            provider_id=provider_id,
            workspace_id=workspace_id,
            project_id=project_id,
            name=name,
            key=key,
            model_id=model_id,
            model_type=model_type.upper(),
            enabled=enabled,
            context_window=context_window,
            max_output_tokens=max_output_tokens,
            supports_streaming=supports_streaming,
            supports_tools=supports_tools,
            supports_json_mode=supports_json_mode,
            supports_vision=supports_vision,
            config_json=config_json or {},
            last_test_status="NOT_TESTED",
        )
        self._session.add(row)
        self._session.flush()
        return row

    def update_model(
        self,
        model_id: uuid.UUID,
        *,
        workspace_id: uuid.UUID,
        project_id: uuid.UUID,
        patch: dict[str, Any],
    ) -> AiModelRow:
        row = self.get_model(model_id, workspace_id=workspace_id, project_id=project_id)
        merged_type = patch.get("model_type", row.model_type)
        merged_model_id = patch.get("model_id", row.model_id)
        if any(k in patch for k in ("model_type", "model_id", "context_window", "max_output_tokens")):
            validate_model_payload(
                model_type=merged_type,
                model_id=merged_model_id,
                context_window=patch.get("context_window", row.context_window),
                max_output_tokens=patch.get("max_output_tokens", row.max_output_tokens),
            )
        for field in (
            "name",
            "model_id",
            "enabled",
            "context_window",
            "max_output_tokens",
            "supports_streaming",
            "supports_tools",
            "supports_json_mode",
            "supports_vision",
        ):
            if field in patch and patch[field] is not None:
                setattr(row, field, patch[field])
        if "model_type" in patch and patch["model_type"]:
            row.model_type = patch["model_type"].upper()
        if "config_json" in patch and patch["config_json"] is not None:
            row.config_json = patch["config_json"]
        row.updated_at = _utcnow()
        self._session.flush()
        return row

    def delete_model(
        self,
        model_id: uuid.UUID,
        *,
        workspace_id: uuid.UUID,
        project_id: uuid.UUID,
    ) -> None:
        row = self.get_model(model_id, workspace_id=workspace_id, project_id=project_id)
        assigned = self._session.execute(
            select(ModelAssignmentRow.id).where(ModelAssignmentRow.model_id == model_id).limit(1)
        ).first()
        if assigned:
            raise AiRegistryError("MODEL_IN_USE", "Model is assigned to a capability", 409)
        self._session.delete(row)

    def model_dict(self, row: AiModelRow) -> dict[str, Any]:
        provider = row.provider if row.provider else self._session.get(AiProviderRow, row.provider_id)
        return {
            "id": str(row.id),
            "provider_id": str(row.provider_id),
            "workspace_id": str(row.workspace_id),
            "project_id": str(row.project_id) if row.project_id else None,
            "name": row.name,
            "key": row.key,
            "model_id": row.model_id,
            "model_type": row.model_type,
            "enabled": row.enabled,
            "capabilities": {
                "streaming": row.supports_streaming,
                "tools": row.supports_tools,
                "json_mode": row.supports_json_mode,
                "vision": row.supports_vision,
            },
            "context_window": row.context_window,
            "max_output_tokens": row.max_output_tokens,
            "config_json": dict(row.config_json or {}),
            "provider_type": provider.provider_type if provider else None,
            "status": "DISABLED" if not row.enabled else (row.last_test_status or "NOT_TESTED"),
            "last_test_at": row.last_test_at,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }

    def _assert_unique_model_key(self, workspace_id: uuid.UUID, project_id: uuid.UUID, key: str) -> None:
        existing = self._session.execute(
            select(AiModelRow).where(
                AiModelRow.workspace_id == workspace_id,
                AiModelRow.project_id == project_id,
                AiModelRow.key == key,
            )
        ).scalar_one_or_none()
        if existing:
            raise AiRegistryError("MODEL_INVALID", f"Model key already exists: {key}", 409)


class ModelAssignmentService:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._models = ModelRegistryService(session)

    def list_assignments(
        self,
        *,
        workspace_id: uuid.UUID,
        project_id: uuid.UUID,
    ) -> list[dict[str, Any]]:
        resolver = ModelAssignmentResolver(self._session)
        out: list[dict[str, Any]] = []
        for cap in sorted(CAPABILITIES):
            out.append(resolver.resolve(capability=cap, workspace_id=workspace_id, project_id=project_id))
        return out

    def put_assignment(
        self,
        *,
        capability: str,
        model_id: uuid.UUID,
        workspace_id: uuid.UUID,
        project_id: uuid.UUID,
        enabled: bool = True,
    ) -> dict[str, Any]:
        cap = capability.upper()
        model = self._models.get_model(model_id, workspace_id=workspace_id, project_id=project_id)
        if not model.enabled:
            raise AiRegistryError("MODEL_DISABLED", "Model is disabled", 409)
        provider = self._session.get(AiProviderRow, model.provider_id)
        if not provider or not provider.enabled:
            raise AiRegistryError("PROVIDER_DISABLED", "Provider is disabled", 409)
        validate_assignment(capability=cap, model_type=model.model_type)
        existing = self._session.execute(
            select(ModelAssignmentRow).where(
                ModelAssignmentRow.workspace_id == workspace_id,
                ModelAssignmentRow.project_id == project_id,
                ModelAssignmentRow.capability == cap,
            )
        ).scalar_one_or_none()
        if existing:
            existing.model_id = model_id
            existing.enabled = enabled
            existing.updated_at = _utcnow()
            row = existing
        else:
            row = ModelAssignmentRow(
                workspace_id=workspace_id,
                project_id=project_id,
                capability=cap,
                model_id=model_id,
                enabled=enabled,
            )
            self._session.add(row)
        self._session.flush()
        return ModelAssignmentResolver(self._session).resolve(
            capability=cap, workspace_id=workspace_id, project_id=project_id
        )

    def delete_project_assignment(
        self,
        *,
        capability: str,
        workspace_id: uuid.UUID,
        project_id: uuid.UUID,
    ) -> dict[str, Any]:
        cap = capability.upper()
        row = self._session.execute(
            select(ModelAssignmentRow).where(
                ModelAssignmentRow.workspace_id == workspace_id,
                ModelAssignmentRow.project_id == project_id,
                ModelAssignmentRow.capability == cap,
            )
        ).scalar_one_or_none()
        if row:
            self._session.delete(row)
            self._session.flush()
        return ModelAssignmentResolver(self._session).resolve(
            capability=cap, workspace_id=workspace_id, project_id=project_id
        )


class ModelAssignmentResolver:
    """Precedence: project assignment → workspace assignment → legacy env fallback (read-only)."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def resolve(
        self,
        *,
        capability: str,
        workspace_id: uuid.UUID,
        project_id: uuid.UUID,
    ) -> dict[str, Any]:
        cap = capability.upper()
        if cap not in CAPABILITIES:
            raise AiRegistryError("INVALID_ASSIGNMENT", f"Unknown capability: {capability}", 422)
        project_row = self._session.execute(
            select(ModelAssignmentRow).where(
                ModelAssignmentRow.workspace_id == workspace_id,
                ModelAssignmentRow.project_id == project_id,
                ModelAssignmentRow.capability == cap,
                ModelAssignmentRow.enabled.is_(True),
            )
        ).scalar_one_or_none()
        if project_row:
            return self._assignment_payload(project_row, source="PROJECT")
        workspace_row = self._session.execute(
            select(ModelAssignmentRow).where(
                ModelAssignmentRow.workspace_id == workspace_id,
                ModelAssignmentRow.project_id.is_(None),
                ModelAssignmentRow.capability == cap,
                ModelAssignmentRow.enabled.is_(True),
            )
        ).scalar_one_or_none()
        if workspace_row:
            return self._assignment_payload(workspace_row, source="WORKSPACE")
        return {
            "capability": cap,
            "model_id": None,
            "model_name": None,
            "provider_type": None,
            "enabled": False,
            "source": "LEGACY_FALLBACK",
            "health": "NOT_CONFIGURED",
        }

    def _assignment_payload(self, row: ModelAssignmentRow, *, source: str) -> dict[str, Any]:
        model = self._session.get(AiModelRow, row.model_id)
        provider = self._session.get(AiProviderRow, model.provider_id) if model else None
        health = "READY"
        if not model or not model.enabled:
            health = "MODEL_DISABLED"
        elif not provider or not provider.enabled:
            health = "PROVIDER_DISABLED"
        elif (provider.last_test_status or "NOT_TESTED") == "FAILED":
            health = "DEGRADED"
        return {
            "capability": row.capability,
            "model_id": str(model.id) if model else None,
            "model_name": model.name if model else None,
            "model_key": model.key if model else None,
            "provider_type": provider.provider_type if provider else None,
            "enabled": row.enabled,
            "source": source,
            "health": health,
        }


class ProviderTestService:
    def __init__(self, session: Session, secrets: SecretResolver | None = None) -> None:
        self._session = session
        self._factory = ProviderAdapterFactory(secrets)
        self._providers = ProviderRegistryService(session, secrets)

    def test_provider(
        self,
        provider_id: uuid.UUID,
        *,
        workspace_id: uuid.UUID,
        project_id: uuid.UUID,
    ) -> dict[str, Any]:
        row = self._providers.get_provider(provider_id, workspace_id=workspace_id, project_id=project_id)
        if not row.enabled:
            raise AiRegistryError("PROVIDER_DISABLED", "Provider is disabled", 409)
        logger.info("provider_test provider_id=%s provider_type=%s", provider_id, row.provider_type)
        adapter = self._factory.create(row)
        result = asyncio.run(adapter.test_connection())
        row.last_test_at = _utcnow()
        row.last_test_status = result.status
        self._record_test_run(
            workspace_id=workspace_id,
            project_id=project_id,
            provider_id=provider_id,
            model_id=None,
            test_type="PROVIDER",
            result=result,
        )
        self._session.flush()
        logger.info(
            "provider_test_done provider_id=%s status=%s latency_ms=%s",
            provider_id,
            result.status,
            result.latency_ms,
        )
        return {
            "status": result.status,
            "latency_ms": result.latency_ms,
            "provider_type": row.provider_type,
            "error_code": result.error_code,
            "message": result.safe_message,
            "metadata": result.metadata,
        }

    def test_model(
        self,
        model_id: uuid.UUID,
        *,
        workspace_id: uuid.UUID,
        project_id: uuid.UUID,
    ) -> dict[str, Any]:
        models = ModelRegistryService(self._session)
        row = models.get_model(model_id, workspace_id=workspace_id, project_id=project_id)
        if not row.enabled:
            raise AiRegistryError("MODEL_DISABLED", "Model is disabled", 409)
        provider = self._providers.get_provider(row.provider_id, workspace_id=workspace_id, project_id=project_id)
        if not provider.enabled:
            raise AiRegistryError("PROVIDER_DISABLED", "Provider is disabled", 409)
        adapter = self._factory.create(provider)
        logger.info("model_test model_id=%s model_type=%s", model_id, row.model_type)
        result = asyncio.run(adapter.validate_model(model_id=row.model_id, model_type=row.model_type))
        row.last_test_at = _utcnow()
        row.last_test_status = result.status
        self._record_test_run(
            workspace_id=workspace_id,
            project_id=project_id,
            provider_id=provider.id,
            model_id=row.id,
            test_type="MODEL",
            result=result,
        )
        self._session.flush()
        logger.info("model_test_done model_id=%s status=%s latency_ms=%s", model_id, result.status, result.latency_ms)
        return {
            "status": result.status,
            "latency_ms": result.latency_ms,
            "model_type": row.model_type,
            "error_code": result.error_code,
            "message": result.safe_message,
            "metadata": result.metadata,
        }

    def list_provider_remote_models(
        self,
        provider_id: uuid.UUID,
        *,
        workspace_id: uuid.UUID,
        project_id: uuid.UUID,
    ) -> dict[str, Any]:
        row = self._providers.get_provider(provider_id, workspace_id=workspace_id, project_id=project_id)
        adapter = self._factory.create(row)
        logger.info("provider_remote_models provider_id=%s provider_type=%s", provider_id, row.provider_type)
        models = asyncio.run(adapter.list_models())
        return {
            "provider_id": str(provider_id),
            "provider_type": row.provider_type,
            "models": models,
        }

    def _record_test_run(
        self,
        *,
        workspace_id: uuid.UUID,
        project_id: uuid.UUID | None,
        provider_id: uuid.UUID,
        model_id: uuid.UUID | None,
        test_type: str,
        result: Any,
    ) -> None:
        self._session.add(
            ModelTestRunRow(
                workspace_id=workspace_id,
                project_id=project_id,
                provider_id=provider_id,
                model_id=model_id,
                test_type=test_type,
                status=result.status,
                latency_ms=int(result.latency_ms) if result.latency_ms is not None else None,
                error_code=result.error_code,
                safe_message=result.safe_message,
                metadata_json=dict(result.metadata or {}),
            )
        )

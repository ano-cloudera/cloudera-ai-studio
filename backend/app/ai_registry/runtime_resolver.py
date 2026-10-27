from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Any, Literal

from sqlalchemy.orm import Session

from app.ai_registry.runtime_errors import RegistryRuntimeError
from app.ai_registry.secrets import SecretResolver
from app.ai_registry.services import ModelAssignmentResolver
from app.ai_registry.types import CAPABILITY_REQUIRED_MODEL_TYPE
from app.db.platform_models import AiModelRow, AiProviderRow

logger = logging.getLogger(__name__)

AssignmentSource = Literal["PROJECT", "WORKSPACE", "LEGACY_FALLBACK"]


@dataclass(frozen=True)
class RuntimeModelResolution:
    source: AssignmentSource
    capability: str
    model_uuid: uuid.UUID | None
    model_key: str | None
    runtime_model_id: str | None
    provider_uuid: uuid.UUID | None
    provider_type: str | None
    provider_key: str | None
    legacy_provider: str | None
    legacy_model: str | None
    assignment_health: str | None = None

    @property
    def uses_registry(self) -> bool:
        return self.source in {"PROJECT", "WORKSPACE"}


def _legacy_provider_label(provider_type: str) -> str:
    ptype = provider_type.upper()
    if ptype == "GEMINI":
        return "gemini"
    if ptype == "OPENAI":
        return "openai"
    if ptype in {"OPENAI_COMPATIBLE", "ANTHROPIC"}:
        return "qwen"
    return "qwen"


class RuntimeModelResolver:
    def __init__(self, session: Session, secrets: SecretResolver | None = None) -> None:
        self._session = session
        self._secrets = secrets or SecretResolver()

    def resolve(
        self,
        *,
        capability: str,
        workspace_id: uuid.UUID,
        project_id: uuid.UUID,
        fallback_provider: str,
        fallback_model: str,
    ) -> RuntimeModelResolution:
        cap = capability.upper()
        assignment = ModelAssignmentResolver(self._session).resolve(
            capability=cap,
            workspace_id=workspace_id,
            project_id=project_id,
        )
        source = assignment.get("source") or "LEGACY_FALLBACK"
        if source == "LEGACY_FALLBACK":
            logger.info(
                "model_resolution capability=%s source=LEGACY_FALLBACK provider=%s model_key=%s",
                cap,
                fallback_provider,
                fallback_model,
            )
            return RuntimeModelResolution(
                source="LEGACY_FALLBACK",
                capability=cap,
                model_uuid=None,
                model_key=None,
                runtime_model_id=fallback_model,
                provider_uuid=None,
                provider_type=None,
                provider_key=None,
                legacy_provider=fallback_provider,
                legacy_model=fallback_model,
                assignment_health=assignment.get("health"),
            )

        health = str(assignment.get("health") or "READY")
        if health in {"MODEL_DISABLED", "PROVIDER_DISABLED"}:
            code = health
            raise RegistryRuntimeError(
                code,
                f"Registry assignment for {cap} is not runnable ({code.lower().replace('_', ' ')})",
                503,
            )

        model_id_raw = assignment.get("model_id")
        if not model_id_raw:
            raise RegistryRuntimeError("MODEL_NOT_FOUND", f"Registry assignment for {cap} is incomplete", 503)
        model = self._session.get(AiModelRow, uuid.UUID(str(model_id_raw)))
        if not model:
            raise RegistryRuntimeError("MODEL_NOT_FOUND", "Assigned model was not found", 503)
        provider = self._session.get(AiProviderRow, model.provider_id)
        if not provider:
            raise RegistryRuntimeError("PROVIDER_NOT_FOUND", "Assigned provider was not found", 503)

        required_type = CAPABILITY_REQUIRED_MODEL_TYPE.get(cap)
        if required_type and model.model_type.upper() != required_type:
            raise RegistryRuntimeError(
                "INVALID_ASSIGNMENT",
                f"Capability {cap} requires model_type {required_type}",
                503,
            )

        legacy = _legacy_provider_label(provider.provider_type)
        logger.info(
            "model_resolution capability=%s source=%s provider_type=%s model_key=%s request_id_context=registry",
            cap,
            source,
            provider.provider_type,
            model.key,
        )
        return RuntimeModelResolution(
            source=source,  # type: ignore[arg-type]
            capability=cap,
            model_uuid=model.id,
            model_key=model.key,
            runtime_model_id=model.model_id,
            provider_uuid=provider.id,
            provider_type=provider.provider_type,
            provider_key=provider.key,
            legacy_provider=legacy,
            legacy_model=model.model_id,
            assignment_health=health,
        )

    def load_provider_row(self, provider_id: uuid.UUID) -> AiProviderRow:
        row = self._session.get(AiProviderRow, provider_id)
        if not row:
            raise RegistryRuntimeError("PROVIDER_NOT_FOUND", "Provider not found", 503)
        return row

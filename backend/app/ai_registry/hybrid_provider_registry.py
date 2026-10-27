from __future__ import annotations

import contextvars
import logging
import uuid
from dataclasses import dataclass
from typing import Any

from app.ai_registry.runtime_errors import RegistryRuntimeError
from app.ai_registry.runtime_llm import build_registry_llm_provider
from app.ai_registry.runtime_resolver import RuntimeModelResolution, RuntimeModelResolver
from app.ai_registry.secrets import SecretResolver
from app.core.config import Settings
from app.llm.registry import ProviderRegistry

logger = logging.getLogger(__name__)


@dataclass
class _RegistryRequestContext:
    capability: str
    workspace_id: uuid.UUID
    project_id: uuid.UUID
    fallback_provider: str
    fallback_model: str
    resolution: RuntimeModelResolution | None = None
    provider_instance: Any | None = None


_ctx: contextvars.ContextVar[_RegistryRequestContext | None] = contextvars.ContextVar(
    "registry_llm_request_ctx",
    default=None,
)


class HybridProviderRegistry:
    """Legacy ProviderRegistry with optional per-request registry assignment override."""

    def __init__(
        self,
        settings: Settings,
        *,
        legacy: ProviderRegistry | None = None,
        session_factory: Any | None = None,
    ) -> None:
        self.settings = settings
        self._legacy = legacy or ProviderRegistry(settings)
        self._session_factory = session_factory
        self._secrets = SecretResolver()
        self.last_resolution: RuntimeModelResolution | None = None

    def clear_request_context(self) -> None:
        _ctx.set(None)
        self.last_resolution = None

    def prepare_request(
        self,
        *,
        capability: str,
        workspace_id: uuid.UUID | str | None,
        project_id: uuid.UUID | str | None,
        fallback_provider: str,
        fallback_model: str,
    ) -> RuntimeModelResolution:
        if self._session_factory is None or not workspace_id or not project_id:
            resolution = RuntimeModelResolution(
                source="LEGACY_FALLBACK",
                capability=capability.upper(),
                model_uuid=None,
                model_key=None,
                runtime_model_id=fallback_model,
                provider_uuid=None,
                provider_type=None,
                provider_key=None,
                legacy_provider=fallback_provider,
                legacy_model=fallback_model,
            )
            _ctx.set(
                _RegistryRequestContext(
                    capability=capability.upper(),
                    workspace_id=uuid.UUID(str(workspace_id)) if workspace_id else uuid.UUID(int=0),
                    project_id=uuid.UUID(str(project_id)) if project_id else uuid.UUID(int=0),
                    fallback_provider=fallback_provider,
                    fallback_model=fallback_model,
                    resolution=resolution,
                )
            )
            self.last_resolution = resolution
            return resolution

        ws = uuid.UUID(str(workspace_id))
        proj = uuid.UUID(str(project_id))
        with self._session_factory() as session:
            resolver = RuntimeModelResolver(session, self._secrets)
            resolution = resolver.resolve(
                capability=capability,
                workspace_id=ws,
                project_id=proj,
                fallback_provider=fallback_provider,
                fallback_model=fallback_model,
            )
            provider_instance = None
            if resolution.uses_registry and resolution.provider_uuid and resolution.model_uuid:
                provider_row = resolver.load_provider_row(resolution.provider_uuid)
                provider_instance = build_registry_llm_provider(
                    settings=self.settings,
                    provider_row=provider_row,
                    resolution=resolution,
                    secrets=self._secrets,
                )
        _ctx.set(
            _RegistryRequestContext(
                capability=capability.upper(),
                workspace_id=ws,
                project_id=proj,
                fallback_provider=fallback_provider,
                fallback_model=fallback_model,
                resolution=resolution,
                provider_instance=provider_instance,
            )
        )
        self.last_resolution = resolution
        return resolution

    def list_models(self):
        return self._legacy.list_models()

    def resolve(self, provider: str, model: str) -> Any:
        ctx = _ctx.get()
        if ctx is None or ctx.resolution is None or not ctx.resolution.uses_registry:
            return self._legacy.resolve(provider, model)
        if ctx.provider_instance is not None:
            return ctx.provider_instance
        raise RegistryRuntimeError("PROVIDER_UNREACHABLE", "Registry provider was not initialized", 503)

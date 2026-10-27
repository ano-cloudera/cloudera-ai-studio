from __future__ import annotations

from typing import Any

from app.ai_registry.adapters.anthropic_adapter import AnthropicAdapter
from app.ai_registry.adapters.base import AIProviderAdapter
from app.ai_registry.adapters.gemini_adapter import GeminiAdapter
from app.ai_registry.adapters.openai_adapter import OpenAIAdapter
from app.ai_registry.adapters.openai_compatible import OpenAICompatibleAdapter
from app.ai_registry.errors import AiRegistryError
from app.ai_registry.secrets import SecretResolver
from app.db.platform_models import AiProviderRow


class ProviderAdapterFactory:
    def __init__(self, secrets: SecretResolver | None = None) -> None:
        self._secrets = secrets or SecretResolver()

    def create(self, row: AiProviderRow) -> AIProviderAdapter:
        config: dict[str, Any] = dict(row.config_json or {})
        ptype = row.provider_type.upper()
        if ptype == "OPENAI":
            if not row.secret_ref:
                raise AiRegistryError("INVALID_SECRET_REF", "OpenAI provider requires secret_ref", 422)
            return OpenAIAdapter(secret_ref=row.secret_ref, base_url=row.base_url, config=config, secrets=self._secrets)
        if ptype == "GEMINI":
            if not row.secret_ref:
                raise AiRegistryError("INVALID_SECRET_REF", "Gemini provider requires secret_ref", 422)
            return GeminiAdapter(secret_ref=row.secret_ref, config=config, secrets=self._secrets)
        if ptype == "ANTHROPIC":
            if not row.secret_ref:
                raise AiRegistryError("INVALID_SECRET_REF", "Anthropic provider requires secret_ref", 422)
            return AnthropicAdapter(secret_ref=row.secret_ref, base_url=row.base_url, config=config, secrets=self._secrets)
        if ptype == "OPENAI_COMPATIBLE":
            if not row.base_url:
                raise AiRegistryError("PROVIDER_UNREACHABLE", "OpenAI-compatible provider requires base_url", 422)
            return OpenAICompatibleAdapter(
                base_url=row.base_url,
                secret_ref=row.secret_ref,
                config=config,
                secrets=self._secrets,
            )
        raise AiRegistryError("PROVIDER_UNREACHABLE", f"Unsupported provider_type: {row.provider_type}", 400)

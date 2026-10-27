from __future__ import annotations

from app.core.config import Settings, get_settings
from app.core.models import ModelInfo
from app.llm.base import LLMProvider
from app.llm.providers import GeminiProvider, OpenAIProvider, QwenProvider


class ProviderSelectionError(ValueError):
    pass


class ProviderRegistry:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def list_models(self) -> list[ModelInfo]:
        qwen_reason = None
        if not self.settings.qwen_model:
            qwen_reason = "Model not configured"
        elif not self.settings.qwen_base_url:
            qwen_reason = "Base URL not configured"
        elif not self.settings.qwen_api_key.get_secret_value():
            qwen_reason = "API key not configured"
        gemini_reason = None
        if not self.settings.gemini_model:
            gemini_reason = "Model not configured"
        elif not self.settings.gemini_api_key.get_secret_value():
            gemini_reason = "API key not configured"
        openai_reason = None
        if not self.settings.openai_model:
            openai_reason = "Model not configured"
        elif not self.settings.openai_api_key.get_secret_value():
            openai_reason = "API key not configured"
        return [
            ModelInfo(provider="qwen", id=self.settings.qwen_model, label="Qwen Private", available=qwen_reason is None, reason=qwen_reason),
            ModelInfo(provider="gemini", id=self.settings.gemini_model, label="Gemini", available=gemini_reason is None, reason=gemini_reason),
            ModelInfo(provider="openai", id=self.settings.openai_model, label="ChatGPT", available=openai_reason is None, reason=openai_reason),
        ]

    def resolve(self, provider: str, model: str) -> LLMProvider:
        match = next((item for item in self.list_models() if item.provider == provider), None)
        if match is None:
            raise ProviderSelectionError("Provider is not configured")
        if model != match.id:
            raise ProviderSelectionError("Model is not configured for this provider")
        if not match.available:
            raise ProviderSelectionError(match.reason or "Provider unavailable")
        implementations = {
            "qwen": QwenProvider,
            "gemini": GeminiProvider,
            "openai": OpenAIProvider,
        }
        return implementations[provider](self.settings)

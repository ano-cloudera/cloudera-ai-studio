from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.ai_registry.adapters.openai_compatible import OpenAICompatibleAdapter
from app.ai_registry.errors import AiRegistryError
from app.ai_registry.secrets import SecretResolver
from app.ai_registry.validation import validate_assignment, validate_provider_payload


def test_validate_provider_openai_requires_secret():
    with pytest.raises(AiRegistryError) as exc:
        validate_provider_payload(provider_type="OPENAI", secret_ref=None, base_url=None)
    assert exc.value.code == "SECRET_NOT_FOUND"


def test_validate_assignment_ask_data_requires_chat():
    validate_assignment(capability="ASK_DATA", model_type="CHAT")
    with pytest.raises(AiRegistryError) as exc:
        validate_assignment(capability="ASK_DATA", model_type="EMBEDDING")
    assert exc.value.code == "INVALID_ASSIGNMENT"


def test_secret_resolver_never_returns_ref_in_error():
    resolver = SecretResolver()
    with pytest.raises(AiRegistryError):
        resolver.resolve("env://MISSING_M7A_KEY")


@pytest.mark.asyncio
async def test_openai_compatible_auth_failure():
    adapter = OpenAICompatibleAdapter(
        base_url="https://example.com/v1",
        secret_ref=None,
        config={"test_strategy": "MODELS_ENDPOINT"},
    )

    mock_resp = MagicMock()
    mock_resp.status_code = 401

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.get = AsyncMock(return_value=mock_resp)

    with patch("app.ai_registry.adapters.openai_compatible.httpx.AsyncClient", return_value=mock_client):
        result = await adapter.test_connection()
    assert result.status == "FAILED"
    assert result.error_code == "AUTHENTICATION_FAILED"
    assert "Bearer" not in (result.safe_message or "")


@pytest.mark.asyncio
async def test_openai_compatible_models_success():
    adapter = OpenAICompatibleAdapter(
        base_url="https://example.com/v1",
        secret_ref="env://QWEN_API_KEY",
        config={"test_strategy": "MODELS_ENDPOINT"},
        secrets=SecretResolver(),
    )
    import os

    os.environ["QWEN_API_KEY"] = "token-not-logged"

    mock_resp = MagicMock()
    mock_resp.status_code = 200

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.get = AsyncMock(return_value=mock_resp)

    with patch("app.ai_registry.adapters.openai_compatible.httpx.AsyncClient", return_value=mock_client):
        result = await adapter.test_connection()
    assert result.status == "READY"
    assert result.metadata.get("endpoint") == "models"

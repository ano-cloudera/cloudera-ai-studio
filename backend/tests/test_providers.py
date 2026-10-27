from __future__ import annotations

import json

import httpx
import pytest
from pydantic import BaseModel

from app.core.config import Settings
from app.core.models import QueryPlan
from app.llm.base import ProviderError
from app.llm.providers import GeminiProvider, OpenAIProvider, QwenProvider
from app.llm.registry import ProviderRegistry


class Result(BaseModel):
    answer: str


def test_qwen_api_token_environment_alias_enables_provider(monkeypatch) -> None:
    monkeypatch.delenv("QWEN_API_KEY", raising=False)
    monkeypatch.setenv("QWEN_API_TOKEN", "dummy")
    monkeypatch.setenv("QWEN_BASE_URL", "https://qwen.internal/v1")
    monkeypatch.setenv("QWEN_MODEL", "/home/cdsw/models/Qwen3.8-27B-AWQ")

    settings = Settings(_env_file=None)
    qwen = ProviderRegistry(settings).list_models()[0]

    assert settings.qwen_api_key.get_secret_value() == "dummy"
    assert qwen.available is True


@pytest.mark.asyncio
async def test_qwen_retries_schema_mismatch_with_exact_response_schema() -> None:
    requests: list[dict] = []
    responses = [
        {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "plan_type": "clarification",
                                "clarification": "Pertanyaan apa yang ingin dianalisis?",
                                "reasoning": "Greeting",
                            }
                        )
                    }
                }
            ]
        },
        {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "strategy": "clarification",
                                "clarification_question": "Pertanyaan apa yang ingin dianalisis?",
                            }
                        )
                    }
                }
            ]
        },
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        return httpx.Response(200, json=responses[len(requests) - 1])

    settings = Settings(
        _env_file=None,
        qwen_base_url="https://qwen.internal/v1",
        qwen_model="qwen-model",
        qwen_api_key="dummy",
    )
    provider = QwenProvider(settings, transport=httpx.MockTransport(handler))

    result = await provider.generate_structured(
        [{"role": "system", "content": "Plan the query."}, {"role": "user", "content": "halo"}],
        QueryPlan,
        temperature=0,
        max_tokens=500,
    )

    assert result.strategy == "clarification"
    assert result.clarification_question == "Pertanyaan apa yang ingin dianalisis?"
    assert len(requests) == 2
    assert '"strategy"' in requests[0]["messages"][0]["content"]
    assert requests[1]["messages"][-2]["role"] == "assistant"
    assert requests[1]["messages"][-1]["role"] == "user"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("provider_type", "provider_name"),
    [(QwenProvider, "qwen"), (OpenAIProvider, "openai")],
)
async def test_openai_compatible_providers_return_validated_structured_output(
    provider_type, provider_name
) -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": '{"answer":"grounded"}'}}]},
        )

    settings = Settings(
        _env_file=None,
        qwen_base_url="https://qwen.internal/v1",
        qwen_model="qwen-model",
        qwen_api_key="qwen-secret",
        openai_base_url="https://openai.example/v1",
        openai_model="openai-model",
        openai_api_key="openai-secret",
    )
    provider = provider_type(settings, transport=httpx.MockTransport(handler))

    result = await provider.generate_structured(
        [{"role": "user", "content": "question"}], Result, temperature=0, max_tokens=123
    )

    assert result == Result(answer="grounded")
    assert captured["model"] == f"{provider_name}-model"
    if provider_name == "openai":
        assert "temperature" not in captured
        assert captured["max_completion_tokens"] == 123
        assert "max_tokens" not in captured
    else:
        assert captured["temperature"] == 0
        assert captured["max_tokens"] == 123


@pytest.mark.asyncio
async def test_gemini_provider_returns_validated_structured_output() -> None:
    from unittest.mock import AsyncMock, MagicMock, patch

    settings = Settings(
        _env_file=None,
        gemini_model="gemini-model",
        gemini_api_key="gemini-secret",
    )
    provider = GeminiProvider(settings)
    mock_response = MagicMock()
    mock_response.text = '{"answer":"grounded"}'
    mock_aio = MagicMock()
    mock_aio.models.generate_content = AsyncMock(return_value=mock_response)
    mock_client = MagicMock()
    mock_client.aio = mock_aio

    captured: dict = {}

    async def _capture_generate(**kwargs):
        captured.update(kwargs)
        return mock_response

    mock_aio.models.generate_content = AsyncMock(side_effect=_capture_generate)

    with patch.object(provider, "_client_instance", return_value=mock_client):
        result = await provider.generate_structured(
            [
                {"role": "system", "content": "system"},
                {"role": "user", "content": "question"},
            ],
            Result,
            temperature=0.2,
            max_tokens=321,
        )

    assert result == Result(answer="grounded")
    mock_aio.models.generate_content.assert_awaited_once()
    assert captured["config"].temperature == 0.2
    assert captured["config"].max_output_tokens == 321


@pytest.mark.asyncio
async def test_qwen_http_error_logs_safe_diagnostics_without_api_token(caplog) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": {"code": "context_length_exceeded", "message": "prompt too long"}})

    settings = Settings(
        _env_file=None,
        qwen_base_url="https://qwen.internal/v1",
        qwen_model="qwen-model",
        qwen_api_key="super-secret-token",
    )
    provider = QwenProvider(settings, transport=httpx.MockTransport(handler))

    with pytest.raises(ProviderError, match="Model provider request failed"):
        await provider.generate_structured(
            [{"role": "user", "content": "question"}], Result, temperature=0, max_tokens=123
        )

    assert "status=400" in caplog.text
    assert "context_length_exceeded" in caplog.text
    assert "super-secret-token" not in caplog.text

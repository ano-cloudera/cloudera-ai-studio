from fastapi.testclient import TestClient
import pytest
from pydantic import SecretStr

from pydantic import SecretStr

from app.core.config import Settings
from app.llm.registry import ProviderRegistry, ProviderSelectionError
from app.main import create_app

from conftest import isolated_settings


def configured_settings() -> Settings:
    return isolated_settings()


def test_health_is_lightweight_and_exact() -> None:
    client = TestClient(create_app(configured_settings()))

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_models_reports_configured_availability_without_secrets() -> None:
    client = TestClient(create_app(configured_settings()))

    response = client.get("/models")

    assert response.status_code == 200
    assert response.json() == {
        "models": [
            {
                "provider": "qwen",
                "id": "/models/Qwen3.8-27B-AWQ",
                "label": "Qwen Private",
                "available": True,
                "reason": None,
            },
            {
                "provider": "gemini",
                "id": "gemini-configured",
                "label": "Gemini",
                "available": False,
                "reason": "API key not configured",
            },
            {
                "provider": "openai",
                "id": "gpt-configured",
                "label": "ChatGPT",
                "available": False,
                "reason": "API key not configured",
            },
        ]
    }
    body = response.text.lower()
    assert "api_key" not in body
    assert "token" not in body


def test_registry_rejects_arbitrary_model_for_valid_provider() -> None:
    registry = ProviderRegistry(configured_settings())

    with pytest.raises(ProviderSelectionError, match="not configured"):
        registry.resolve("qwen", "attacker-controlled-model")


def test_registry_rejects_unavailable_provider() -> None:
    registry = ProviderRegistry(configured_settings())

    with pytest.raises(ProviderSelectionError, match="API key not configured"):
        registry.resolve("gemini", "gemini-configured")


def test_qwen_requires_a_credential_by_default() -> None:
    settings = isolated_settings(qwen_api_key=SecretStr(""))
    response = TestClient(create_app(settings)).get("/models")

    qwen = next(model for model in response.json()["models"] if model["provider"] == "qwen")
    assert qwen["available"] is False
    assert qwen["reason"] == "API key not configured"


def test_readiness_endpoint_is_safe_and_component_aware() -> None:
    settings = isolated_settings(impala_host="", impala_user="")
    response = TestClient(create_app(settings)).get("/health/ready")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "not_ready"
    assert body["components"]["llm"] == "ready"
    assert body["components"]["impala"] == "not_configured"
    assert body["components"]["semantic"] == "ready"
    assert "gemini_model" in body["components"]
    assert "ask_data_routing" in body["components"]


def test_readiness_accepts_gssapi_identity_from_kerberos_ticket() -> None:
    settings = isolated_settings(
        impala_host="impala.internal",
        impala_auth_mechanism="GSSAPI",
        impala_user="",
        impala_kerberos_service_name="impala",
    )
    response = TestClient(create_app(settings)).get("/health/ready")

    assert response.status_code == 200
    assert response.json()["components"]["impala"] == "ready"

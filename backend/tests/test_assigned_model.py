"""The model assigned in Settings -> AI Models is what the UI offers and what /chat accepts, with no environment variables."""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import SecretStr

from app.ai_registry.hybrid_provider_registry import HybridProviderRegistry
from app.ai_registry.runtime_resolver import RuntimeModelResolution
from app.api import chat as chat_api
from app.api import models as models_api
from app.core.models import AskDataRequest, ModelInfo
from conftest import isolated_settings

ASSIGNED = ModelInfo(provider="qwen", id="Qwen3.5-9B", label="qwen3.5-9b", available=True, assigned=True)


def _app(registry, assigned):
    chat_service = SimpleNamespace(assigned_model=lambda mode="ask_data": assigned)
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(provider_registry=registry, chat_service=chat_service)))


def _registry(*, gemini_key: str = "k") -> HybridProviderRegistry:
    # No QWEN_* variables, like a private vLLM that exists only in the registry.
    return HybridProviderRegistry(isolated_settings(qwen_model="", qwen_base_url="", gemini_api_key=SecretStr(gemini_key)))


def _request(provider: str = "gemini", model: str = "gemini-2.5-flash") -> AskDataRequest:
    return AskDataRequest(session_id="s", question="q", provider=provider, model=model)  # type: ignore[arg-type]


def test_the_assigned_model_leads_the_list_and_replaces_the_environment_entry_of_its_provider() -> None:
    listed = models_api.models(_app(_registry(), ASSIGNED)).models
    assert listed[0] == ASSIGNED and [m.provider for m in listed].count("qwen") == 1
    assert {m.provider for m in listed} == {"qwen", "gemini", "openai"}
    plain = models_api.models(_app(_registry(), None)).models
    qwen = next(m for m in plain if m.provider == "qwen")
    assert not qwen.available and not qwen.assigned  # without an assignment Qwen needs its environment variables


def test_a_selection_is_accepted_when_a_model_is_assigned_even_if_the_environment_has_none() -> None:
    registry = _registry(gemini_key="")
    assert not any(m.available for m in registry.list_models())
    chat_api._validate_selection(_app(registry, ASSIGNED), _request())  # the assigned model answers
    with pytest.raises(HTTPException) as refused:
        chat_api._validate_selection(_app(registry, None), _request())
    assert refused.value.status_code == 422


def test_the_assignment_is_read_as_the_provider_and_model_the_ui_sends(monkeypatch) -> None:
    from app.services.chat import ChatService

    registry = _registry()
    resolution = RuntimeModelResolution(
        source="PROJECT", capability="ASK_DATA", model_uuid=None, model_key="qwen3.5-9b", runtime_model_id="Qwen3.5-9B",
        provider_uuid=None, provider_type="OPENAI_COMPATIBLE", provider_key="vllm", legacy_provider="qwen", legacy_model="Qwen3.5-9B",
    )
    service = ChatService.__new__(ChatService)
    service.dependencies = SimpleNamespace(provider_registry=registry)

    def prepare(self, request, *, capability):
        registry.last_resolution = resolution if capability == "ASK_DATA" else None
        return request

    monkeypatch.setattr(ChatService, "_prepare_registry_request", prepare)
    found = service.assigned_model("ask_data")
    assert found and (found.provider, found.id, found.label, found.assigned, found.available) == ("qwen", "Qwen3.5-9B", "qwen3.5-9b", True, True)
    assert registry.last_resolution is None  # the probe leaves no request context behind
    assert service.assigned_model("rag") is None

    monkeypatch.setattr(ChatService, "_prepare_registry_request", lambda self, request, *, capability: (_ for _ in ()).throw(RuntimeError("disabled")))
    assert service.assigned_model("ask_data") is None  # a broken assignment is reported when it runs, not when listing
    service.dependencies = SimpleNamespace(provider_registry=object())
    assert service.assigned_model("ask_data") is None  # no registry at all


def test_readiness_counts_an_assigned_model_when_no_environment_model_exists() -> None:
    from app.platform.readiness import build_readiness_report

    registry = _registry(gemini_key="")
    without = build_readiness_report(isolated_settings(), provider_registry=registry)
    with_assignment = build_readiness_report(isolated_settings(), provider_registry=registry, assigned_model_ready=True)
    assert without["components"]["llm"] == "not_configured"
    assert with_assignment["components"]["llm"] == "ready"


def test_the_answer_carries_the_name_the_model_has_in_ai_models() -> None:
    """The footer under an answer names the model that ran; the provider bucket ('qwen' for any OpenAI-compatible endpoint) does not."""
    from app.services.chat import ChatService

    registry = _registry()
    registry.last_resolution = RuntimeModelResolution(
        source="PROJECT", capability="ASK_DATA", model_uuid=None, model_key="nemotron_super", runtime_model_id="nvidia/nemotron-3-super-120b-a12b",
        provider_uuid=None, provider_type="OPENAI_COMPATIBLE", provider_key="nemotron", legacy_provider="qwen",
        legacy_model="nvidia/nemotron-3-super-120b-a12b", model_name="nvidia/nemotron-3-super-120b-a12b", provider_name="nemotron",
    )
    service = ChatService.__new__(ChatService)
    service.dependencies = SimpleNamespace(provider_registry=registry)
    meta = service._resolution_meta_from_registry()
    assert meta is not None and (meta.model_name, meta.provider_name, meta.model_key) == ("nvidia/nemotron-3-super-120b-a12b", "nemotron", "nemotron_super")

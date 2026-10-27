from __future__ import annotations

from unittest.mock import MagicMock

from app.core.config import Settings
from app.platform.readiness import build_readiness_report


def _settings(**overrides) -> Settings:
    base = dict(
        _env_file=None,
        state_store="postgres",
        database_url="postgresql+psycopg://u:p@127.0.0.1:9/none",
        feature_profile="FULL_ACCELERATOR",
        data_backend="impala",
        impala_host="",
        impala_user="",
        document_storage_root="/tmp/cas-doc-storage-test",
        semantic_runtime_storage_root="/tmp/cas-sem-runtime-test",
        qdrant_url="",
        embedding_provider="mock",
        reranker_provider="none",
    )
    base.update(overrides)
    return Settings(**base)


def _registry(*, llm_available: bool = False) -> MagicMock:
    model = MagicMock()
    model.available = llm_available
    reg = MagicMock()
    reg.list_models.return_value = [model] if llm_available else []
    return reg


def test_fresh_install_no_datasource_no_llm_not_degraded(monkeypatch) -> None:
    """Clean post-cleanup env: unconfigured Ask Data paths are not platform gaps."""
    monkeypatch.setattr(
        "app.platform.readiness._postgres_check",
        lambda _s: {"status": "ready"},
    )
    report = build_readiness_report(_settings(), provider_registry=_registry(llm_available=False))
    assert report["core_ready"] is True
    assert report["feature_gaps"] == []
    assert report["status"] == "ready"
    assert report["components"]["llm"] == "not_configured"
    assert report["components"]["legacy_datasource"] == "not_configured"


def test_optional_qdrant_not_configured_not_a_gap(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.platform.readiness._postgres_check",
        lambda _s: {"status": "ready"},
    )
    report = build_readiness_report(_settings(qdrant_url=""), provider_registry=_registry())
    assert "rag_needs_qdrant" not in report["feature_gaps"]
    assert report["status"] == "ready"


def test_qdrant_not_ready_is_platform_gap(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.platform.readiness._postgres_check",
        lambda _s: {"status": "ready"},
    )
    monkeypatch.setattr(
        "app.vectors.store.build_vector_store",
        lambda _s: MagicMock(health=lambda: {"status": "not_ready", "error": "timeout"}),
    )
    report = build_readiness_report(_settings(qdrant_url="http://127.0.0.1:6333"), provider_registry=_registry())
    assert "rag_needs_qdrant" in report["feature_gaps"]
    assert report["status"] == "not_ready"
    assert report["core_ready"] is True


def test_postgres_not_ready_core_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.platform.readiness._postgres_check",
        lambda _s: {"status": "not_ready", "error": "OperationalError"},
    )
    report = build_readiness_report(_settings(), provider_registry=_registry())
    assert report["core_ready"] is False
    assert report["status"] == "not_ready"


def test_llm_available_legacy_optional_still_ready(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.platform.readiness._postgres_check",
        lambda _s: {"status": "ready"},
    )
    report = build_readiness_report(_settings(), provider_registry=_registry(llm_available=True))
    assert report["core_ready"] is True
    assert report["feature_gaps"] == []
    assert report["status"] == "ready"

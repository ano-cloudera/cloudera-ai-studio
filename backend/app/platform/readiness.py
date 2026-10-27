from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from app.core.config import Settings
from app.db.duckdb_governed_backend import is_duckdb_governed_configured
from app.db.impala_backend import is_impala_configured
from app.platform.accelerator import (
    ACCELERATOR_VERSION,
    ask_data_enabled_for_profile,
    normalize_feature_profile,
    rag_enabled_for_profile,
)


def _storage_check(path: Path) -> dict[str, Any]:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".write_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return {"status": "ready", "path": str(path)}
    except OSError as exc:
        return {"status": "not_ready", "path": str(path), "error": type(exc).__name__}


def _postgres_check(settings: Settings) -> dict[str, Any]:
    url = (settings.database_url or "").strip()
    if not url:
        return {"status": "not_configured"}
    try:
        from sqlalchemy import create_engine, text

        engine = create_engine(url, pool_pre_ping=True)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ready"}
    except Exception as exc:
        return {"status": "not_ready", "error": type(exc).__name__}


def build_readiness_report(settings: Settings, *, provider_registry: Any) -> dict[str, Any]:
    profile = normalize_feature_profile(getattr(settings, "feature_profile", "FULL_ACCELERATOR"))
    state_store = settings.state_store.strip().lower()
    use_duckdb = settings.data_backend.strip().lower() == "duckdb"
    legacy_datasource_ready = (
        is_duckdb_governed_configured(settings) if use_duckdb else is_impala_configured(settings)
    )
    llm_ready = any(model.available for model in provider_registry.list_models())

    postgres = _postgres_check(settings) if state_store == "postgres" else {"status": "not_required"}
    document_storage = _storage_check(Path(settings.document_storage_root))
    semantic_runtime = _storage_check(Path(settings.semantic_runtime_storage_root))

    qdrant: dict[str, Any]
    try:
        from app.vectors.store import build_vector_store

        store = build_vector_store(settings)
        qdrant = store.health() if store else {"status": "not_configured"}
    except Exception as exc:
        qdrant = {"status": "not_ready", "error": type(exc).__name__}

    embeddings: dict[str, Any]
    try:
        from app.embeddings.provider import get_embedding_provider

        embeddings = get_embedding_provider(settings).health()
    except Exception as exc:
        embeddings = {"status": "not_ready", "error": type(exc).__name__}

    reranker: dict[str, Any]
    try:
        from app.rerank.provider import get_reranker

        reranker = get_reranker(settings).health()
    except Exception as exc:
        reranker = {"status": "not_ready", "error": type(exc).__name__}

    components: dict[str, Any] = {
        "backend": {"status": "ready"},
        "accelerator_version": ACCELERATOR_VERSION,
        "deployment_profile": getattr(settings, "deployment_profile", "local"),
        "feature_profile": profile,
        "state_store": state_store,
        "postgres": postgres,
        "document_storage": document_storage,
        "semantic_runtime_storage": semantic_runtime,
        "llm": "ready" if llm_ready else "not_configured",
        "legacy_datasource": "ready" if legacy_datasource_ready else "not_configured",
        "data_backend": settings.data_backend.strip().lower(),
        "qdrant": qdrant,
        "embeddings": embeddings,
        "reranker": reranker,
        "connectors": {"status": "optional", "note": "Configure via Connector Manager"},
    }

    core_ok = True
    if state_store == "postgres":
        core_ok = postgres.get("status") == "ready"
    if document_storage.get("status") != "ready" or semantic_runtime.get("status") != "ready":
        core_ok = False

    feature_gaps: list[str] = []
    if ask_data_enabled_for_profile(profile) and not llm_ready and not legacy_datasource_ready:
        feature_gaps.append("ask_data_needs_llm_or_datasource")
    if rag_enabled_for_profile(profile):
        q_status = str(qdrant.get("status", ""))
        if q_status not in {"ready", "ok"}:
            feature_gaps.append("rag_needs_qdrant")
        emb_status = str(embeddings.get("status", ""))
        if emb_status not in {"ready", "ok", "mock"}:
            feature_gaps.append("rag_needs_embeddings")

    ready = core_ok and not feature_gaps
    return {
        "status": "ready" if ready else "not_ready",
        "core_ready": core_ok,
        "feature_gaps": feature_gaps,
        "components": components,
    }


def validate_startup_config(settings: Settings) -> None:
    state_store = settings.state_store.strip().lower()
    if state_store == "postgres" and not (settings.database_url or "").strip():
        raise RuntimeError(
            "STATE_STORE=postgres requires DATABASE_URL. "
            "Set DATABASE_URL to the accelerator platform PostgreSQL (not a business datasource)."
        )
    profile = normalize_feature_profile(getattr(settings, "feature_profile", "FULL_ACCELERATOR"))
    if rag_enabled_for_profile(profile) and not (settings.qdrant_url or "").strip():
        # Warning only — RAG endpoints will fail until configured
        import logging

        logging.getLogger(__name__).warning(
            "FEATURE_PROFILE=%s but QDRANT_URL is empty; RAG features will be unavailable until configured.",
            profile,
        )

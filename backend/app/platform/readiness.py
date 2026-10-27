from __future__ import annotations

from pathlib import Path
from typing import Any

from app.core.config import Settings
from app.db.duckdb_governed_backend import is_duckdb_governed_configured
from app.db.impala_backend import is_impala_configured
from app.db.metadata_db import (
    is_sqlite_metadata_url,
    metadata_dialect_name,
    platform_metadata_configured,
    validate_sqlite_single_worker,
)
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


def _component_unhealthy(status: str) -> bool:
    """True when a component was expected to work but is failing (not merely unconfigured)."""
    return status in {"not_ready", "error", "failed", "unhealthy"}


def _metadata_database_check(settings: Settings) -> dict[str, Any]:
    url = (settings.database_url or "").strip()
    if not url:
        return {"status": "not_configured"}
    dialect = metadata_dialect_name(url)
    if dialect not in {"postgresql", "sqlite"}:
        return {"status": "not_ready", "error": "unsupported_dialect", "dialect": dialect}
    try:
        from sqlalchemy import create_engine, text

        from app.db.platform_engine import get_platform_engine

        engine = get_platform_engine(url)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        out: dict[str, Any] = {"status": "ready", "dialect": dialect}
        if dialect == "sqlite":
            out["path"] = url
        return out
    except Exception as exc:
        return {"status": "not_ready", "error": type(exc).__name__, "dialect": dialect}


# Backward-compatible name for tests and ops docs.
_postgres_check = _metadata_database_check


def build_readiness_report(settings: Settings, *, provider_registry: Any) -> dict[str, Any]:
    profile = normalize_feature_profile(getattr(settings, "feature_profile", "FULL_ACCELERATOR"))
    state_store = settings.state_store.strip().lower()
    use_duckdb = settings.data_backend.strip().lower() == "duckdb"
    legacy_datasource_ready = (
        is_duckdb_governed_configured(settings) if use_duckdb else is_impala_configured(settings)
    )
    llm_ready = any(model.available for model in provider_registry.list_models())

    metadata_db = _postgres_check(settings) if platform_metadata_configured(settings) else {"status": "not_configured"}
    # Backward-compatible readiness key (same payload as metadata_db).
    postgres = metadata_db

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
        "metadata_database": metadata_db,
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
    if platform_metadata_configured(settings):
        core_ok = metadata_db.get("status") == "ready"
    elif state_store == "postgres":
        core_ok = False
    if document_storage.get("status") != "ready" or semantic_runtime.get("status") != "ready":
        core_ok = False

    feature_gaps: list[str] = []
    if rag_enabled_for_profile(profile):
        q_status = str(qdrant.get("status", ""))
        if _component_unhealthy(q_status):
            feature_gaps.append("rag_needs_qdrant")
        emb_status = str(embeddings.get("status", ""))
        if _component_unhealthy(emb_status):
            feature_gaps.append("rag_needs_embeddings")
        rerank_status = str(reranker.get("status", ""))
        if _component_unhealthy(rerank_status):
            feature_gaps.append("rag_needs_reranker")

    ready = core_ok and not feature_gaps
    return {
        "status": "ready" if ready else "not_ready",
        "core_ready": core_ok,
        "feature_gaps": feature_gaps,
        "components": components,
    }


def validate_startup_config(settings: Settings) -> None:
    url = (settings.database_url or "").strip()
    state_store = settings.state_store.strip().lower()
    if state_store == "postgres" and not url:
        raise RuntimeError(
            "STATE_STORE=postgres requires DATABASE_URL. "
            "Set DATABASE_URL to the platform metadata database (not a business datasource)."
        )
    if url:
        dialect = metadata_dialect_name(url)
        if dialect not in {"postgresql", "sqlite"}:
            raise RuntimeError(f"Unsupported DATABASE_URL dialect for platform metadata: {dialect}")
        if is_sqlite_metadata_url(url):
            validate_sqlite_single_worker(url)
            db_path = url
            if "///" in url:
                from app.db.metadata_db import sqlite_metadata_path_from_url

                fs_path = sqlite_metadata_path_from_url(url)
                if fs_path:
                    parent = Path(fs_path).expanduser().resolve().parent
                    if not parent.exists():
                        try:
                            parent.mkdir(parents=True, exist_ok=True)
                        except OSError as exc:
                            raise RuntimeError(f"SQLite metadata directory not writable: {parent}") from exc
    profile = normalize_feature_profile(getattr(settings, "feature_profile", "FULL_ACCELERATOR"))
    if rag_enabled_for_profile(profile) and not (settings.qdrant_url or "").strip():
        import logging

        logging.getLogger(__name__).warning(
            "FEATURE_PROFILE=%s but QDRANT_URL is empty; RAG features will be unavailable until configured.",
            profile,
        )

"""Standalone repo path resolution (post-migration storage roots)."""
from __future__ import annotations

from pathlib import Path

from app.core.config import BACKEND_ROOT, Settings, _resolve_backend_relative


def test_resolve_strips_duplicate_backend_prefix():
    resolved = _resolve_backend_relative(Path("backend/runtime/document_storage"))
    assert resolved == (BACKEND_ROOT / "runtime" / "document_storage").resolve()


def test_get_settings_document_storage_not_double_backend():
    settings = Settings.model_construct(
        _env_file=None,
        document_storage_root=Path("backend/runtime/document_storage"),
        semantic_runtime_storage_root=Path("backend/var/semantic-runtime"),
        duckdb_path=BACKEND_ROOT / "runtime" / "tempo_gold_local.duckdb",
    )
    from app.core import config as config_mod

    config_mod.get_settings.cache_clear()
    try:
        # Mirror get_settings relative-path branch without loading .env
        doc = _resolve_backend_relative(Path(settings.document_storage_root))
        sem = _resolve_backend_relative(Path(settings.semantic_runtime_storage_root))
    finally:
        config_mod.get_settings.cache_clear()
    assert "backend/backend" not in str(doc)
    assert doc == (BACKEND_ROOT / "runtime" / "document_storage").resolve()
    assert sem == (BACKEND_ROOT / "var" / "semantic-runtime").resolve()

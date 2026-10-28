from __future__ import annotations

from pathlib import Path

from app.core.config import Settings, BACKEND_ROOT
from app.projects.resolver import resolve_ossie_project_dir


def test_resolve_ossie_legacy_sqlite_mode():
    settings = Settings(_env_file=None, state_store="sqlite", database_url="", ossie_project_id="reference_impala")
    path = resolve_ossie_project_dir(settings)
    expected = (settings.project_root / settings.ossie_project_id).resolve()
    assert path == expected
    assert path.is_dir()


def test_resolve_ossie_postgres_without_db_falls_back():
    settings = Settings(
        _env_file=None,
        state_store="postgres",
        database_url="",
        ossie_project_id="reference_impala",
    )
    path = resolve_ossie_project_dir(settings)
    assert path == (settings.project_root / "reference_impala").resolve()

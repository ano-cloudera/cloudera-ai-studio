#!/usr/bin/env python3
"""Idempotent platform seed after migrations."""
from __future__ import annotations

from app.core.config import Settings, get_settings
from app.db.platform_engine import get_session_factory
from app.projects.bootstrap import ensure_platform_seed
from app.stores.factory import init_postgres_platform


def main() -> None:
    settings = get_settings()
    init_postgres_platform(settings)
    if not (settings.database_url or "").strip():
        print("No DATABASE_URL — sqlite mode uses file stores only.")
        return
    factory = get_session_factory(settings.database_url)
    slug = (settings.default_project_slug or settings.ossie_project_id or "tempo_scan_impala").strip()
    with factory() as session:
        ws, project = ensure_platform_seed(
            session,
            backend_root=settings.project_root.parent,
            project_slug=slug,
        )
    print(f"OK workspace={ws.slug} project={project.slug}")


if __name__ == "__main__":
    main()

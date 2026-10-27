#!/usr/bin/env python3
"""Import existing OSSIE YAML into PostgreSQL semantic registry (DRAFT only)."""

from __future__ import annotations

import argparse
import sys

from app.core.config import BACKEND_ROOT, get_settings
from app.db.platform_engine import get_session_factory
from app.projects.bootstrap import ensure_platform_seed
from app.projects.resolver import resolve_ossie_project_dir
from app.semantic_registry.importer import OssieImporter
from app.services.semantic_registry_service import SemanticModelCreate, SemanticRegistryService


def main() -> int:
    parser = argparse.ArgumentParser(description="Import OSSIE semantics into registry draft.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--model-key", default="commercial_semantic")
    parser.add_argument("--model-name", default="Commercial Semantic Model")
    args = parser.parse_args()

    settings = get_settings()
    url = (settings.database_url or "").strip()
    if settings.state_store.strip().lower() != "postgres" or not url:
        print("STATE_STORE=postgres and DATABASE_URL required", file=sys.stderr)
        return 1

    project_dir = resolve_ossie_project_dir(settings)
    factory = get_session_factory(url)
    with factory() as session:
        _ws, project = ensure_platform_seed(session, backend_root=BACKEND_ROOT)
        svc = SemanticRegistryService(session)
        model = svc._find_model(project.id, args.model_key)
        if not model:
            model = svc.create_model(
                SemanticModelCreate(
                    name=args.model_name,
                    key=args.model_key,
                    workspace_id=project.workspace_id,
                    project_id=project.id,
                    description="Imported from OSSIE (read-only bootstrap)",
                )
            )
        importer = OssieImporter(session)
        summary = importer.import_into_model(model=model, project_dir=project_dir, dry_run=args.dry_run)
        if not args.dry_run:
            session.commit()
    print(summary.to_dict())
    return 0 if not summary.errors else 1


if __name__ == "__main__":
    raise SystemExit(main())

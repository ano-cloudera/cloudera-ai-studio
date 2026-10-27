#!/usr/bin/env python3
"""Idempotent dev connector seed (config only — secrets via env:// references)."""

from __future__ import annotations

import os
import sys

from app.core.config import BACKEND_ROOT, get_settings
from app.db.platform_engine import get_session_factory
from app.connectors.service import ConnectorRegistryService
from app.projects.bootstrap import ensure_platform_seed
from app.projects.resolver import load_default_project


def main() -> int:
    settings = get_settings()
    url = (settings.database_url or "").strip()
    if settings.state_store.strip().lower() != "postgres" or not url:
        print("Requires STATE_STORE=postgres and DATABASE_URL", file=sys.stderr)
        return 1
    project = load_default_project(settings)
    if not project:
        print("Default project not seeded", file=sys.stderr)
        return 1

    factory = get_session_factory(url)
    with factory() as session:
        ensure_platform_seed(session, backend_root=BACKEND_ROOT)
        svc = ConnectorRegistryService(session, settings=settings)
        seeds = [
            {
                "key": "tempo_impala",
                "name": "Tempo Impala",
                "connector_type": "impala",
                "config": {
                    "host": os.environ.get("DEV_IMPALA_HOST", settings.impala_host),
                    "port": int(os.environ.get("DEV_IMPALA_PORT", settings.impala_port)),
                    "database": os.environ.get("DEV_IMPALA_DATABASE", settings.impala_database),
                    "auth_type": "plain",
                    "username": os.environ.get("DEV_IMPALA_USER", settings.impala_user or "impala"),
                },
                "secret_ref": "env://CONNECTOR_TEMPO_IMPALA_PASSWORD",
            },
            {
                "key": "cdw_trino",
                "name": "CDW Trino",
                "connector_type": "trino",
                "config": {
                    "host": os.environ.get("DEV_TRINO_HOST", settings.trino_host or "localhost"),
                    "port": int(os.environ.get("DEV_TRINO_PORT", settings.trino_port)),
                    "catalog": os.environ.get("DEV_TRINO_CATALOG", settings.trino_catalog or "memory"),
                    "username": os.environ.get("DEV_TRINO_USER", settings.trino_user or "trino"),
                },
                "secret_ref": "env://CONNECTOR_TRINO_PASSWORD",
            },
            {
                "key": "local_postgres",
                "name": "Local Demo PostgreSQL",
                "connector_type": "postgres",
                "config": {
                    "host": os.environ.get("DEV_POSTGRES_HOST", "127.0.0.1"),
                    "port": int(os.environ.get("DEV_POSTGRES_PORT", "55432")),
                    "database": os.environ.get("DEV_POSTGRES_DATABASE", "demo_sales"),
                    "username": os.environ.get("DEV_POSTGRES_USER", "demo_sales"),
                    "sslmode": "prefer",
                },
                "secret_ref": "env://DEMO_POSTGRES_PASSWORD",
            },
        ]
        for item in seeds:
            existing = [
                c
                for c in svc.list_connectors(workspace_id=project.workspace_id, project_id=project.id)
                if c.key == item["key"]
            ]
            if existing:
                print(f"skip existing connector key={item['key']}")
                continue
            svc.create_connector(
                workspace_id=project.workspace_id,
                project_id=project.id,
                name=item["name"],
                key=item["key"],
                connector_type=item["connector_type"],
                config=item["config"],
                secret_ref=item["secret_ref"],
            )
            print(f"created connector key={item['key']}")
        session.commit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

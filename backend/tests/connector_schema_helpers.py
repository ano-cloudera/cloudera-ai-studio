from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Engine


def ensure_c1_connectors_schema(engine: Engine) -> None:
    if engine.dialect.name == "sqlite":
        return
    stmts = [
        """
        CREATE TABLE IF NOT EXISTS connectors (
            id UUID PRIMARY KEY,
            workspace_id UUID NOT NULL REFERENCES workspaces(id),
            project_id UUID NOT NULL REFERENCES projects(id),
            name VARCHAR(256) NOT NULL,
            key VARCHAR(128) NOT NULL,
            description TEXT,
            connector_type VARCHAR(32) NOT NULL,
            status VARCHAR(32) NOT NULL,
            enabled BOOLEAN NOT NULL DEFAULT true,
            config JSONB NOT NULL DEFAULT '{}'::jsonb,
            secret_ref VARCHAR(512),
            created_by VARCHAR(256),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            last_tested_at TIMESTAMPTZ,
            last_test_status VARCHAR(32),
            last_test_message TEXT,
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            UNIQUE (workspace_id, project_id, key)
        )
        """,
        "CREATE INDEX IF NOT EXISTS ix_connectors_workspace_project ON connectors (workspace_id, project_id)",
        "CREATE INDEX IF NOT EXISTS ix_connectors_type ON connectors (connector_type)",
        "CREATE INDEX IF NOT EXISTS ix_connectors_status ON connectors (status)",
        "CREATE INDEX IF NOT EXISTS ix_connectors_enabled ON connectors (enabled)",
    ]
    with engine.begin() as conn:
        for stmt in stmts:
            conn.execute(text(stmt))

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Engine


def _alembic_platform_schema(engine: Engine) -> bool:
    """When True, platform tables come from Alembic (SQLite CAI sim / fresh migrates)."""
    return engine.dialect.name == "sqlite"


def ensure_s3_governance_schema(engine: Engine) -> None:
    """Apply S3 DDL idempotently for integration tests (create_all + partial migrations)."""
    if _alembic_platform_schema(engine):
        return
    stmts = [
        "ALTER TABLE semantic_versions ADD COLUMN IF NOT EXISTS last_validation_run_id UUID",
        "ALTER TABLE semantic_versions ADD COLUMN IF NOT EXISTS activation_readiness VARCHAR(32)",
        "ALTER TABLE semantic_versions ADD COLUMN IF NOT EXISTS validated_at TIMESTAMPTZ",
        """
        CREATE TABLE IF NOT EXISTS semantic_validation_runs (
            id UUID PRIMARY KEY,
            semantic_version_id UUID NOT NULL REFERENCES semantic_versions(id) ON DELETE CASCADE,
            started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            completed_at TIMESTAMPTZ,
            status VARCHAR(32) NOT NULL,
            mode VARCHAR(32) NOT NULL DEFAULT 'full',
            summary JSONB NOT NULL DEFAULT '{}'::jsonb,
            validator_version VARCHAR(32) NOT NULL,
            created_by VARCHAR(256)
        )
        """,
        "CREATE INDEX IF NOT EXISTS ix_semantic_validation_runs_version ON semantic_validation_runs (semantic_version_id)",
        """
        CREATE TABLE IF NOT EXISTS semantic_validation_issues (
            id UUID PRIMARY KEY,
            validation_run_id UUID NOT NULL REFERENCES semantic_validation_runs(id) ON DELETE CASCADE,
            severity VARCHAR(16) NOT NULL,
            category VARCHAR(32) NOT NULL,
            object_type VARCHAR(32),
            object_key VARCHAR(128),
            code VARCHAR(64) NOT NULL,
            message TEXT NOT NULL,
            remediation TEXT,
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb
        )
        """,
        "CREATE INDEX IF NOT EXISTS ix_semantic_validation_issues_run ON semantic_validation_issues (validation_run_id)",
        """
        CREATE TABLE IF NOT EXISTS semantic_test_cases (
            id UUID PRIMARY KEY,
            semantic_version_id UUID NOT NULL REFERENCES semantic_versions(id) ON DELETE CASCADE,
            name VARCHAR(256) NOT NULL,
            question TEXT NOT NULL,
            expected_metric_keys JSONB NOT NULL DEFAULT '[]'::jsonb,
            expected_dimension_keys JSONB NOT NULL DEFAULT '[]'::jsonb,
            expected_entity_keys JSONB NOT NULL DEFAULT '[]'::jsonb,
            enabled BOOLEAN NOT NULL DEFAULT true,
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb
        )
        """,
        "CREATE INDEX IF NOT EXISTS ix_semantic_test_cases_version ON semantic_test_cases (semantic_version_id)",
    ]
    with engine.begin() as conn:
        for stmt in stmts:
            conn.execute(text(stmt))


def ensure_c4_semantic_connection_schema(engine: Engine) -> None:
    if _alembic_platform_schema(engine):
        return
    stmts = [
        "ALTER TABLE semantic_entities ADD COLUMN IF NOT EXISTS connection_id UUID",
        """
        DO $$ BEGIN
          ALTER TABLE semantic_entities
            ADD CONSTRAINT fk_semantic_entities_connection_id
            FOREIGN KEY (connection_id) REFERENCES connectors(id) ON DELETE RESTRICT;
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
        """,
        "CREATE INDEX IF NOT EXISTS ix_semantic_entities_connection_id ON semantic_entities (connection_id)",
    ]
    with engine.begin() as conn:
        for stmt in stmts:
            conn.execute(text(stmt))


def ensure_s4_runtime_schema(engine: Engine) -> None:
    """Apply S4 DDL idempotently for integration tests."""
    if _alembic_platform_schema(engine):
        return
    stmts = [
        """
        CREATE TABLE IF NOT EXISTS semantic_runtime_deployments (
            id UUID PRIMARY KEY,
            workspace_id UUID NOT NULL REFERENCES workspaces(id),
            project_id UUID NOT NULL REFERENCES projects(id),
            semantic_model_id UUID NOT NULL REFERENCES semantic_models(id) ON DELETE CASCADE,
            semantic_version_id UUID NOT NULL REFERENCES semantic_versions(id),
            runtime_adapter VARCHAR(64) NOT NULL,
            artifact_uri TEXT NOT NULL,
            artifact_checksum VARCHAR(128) NOT NULL,
            status VARCHAR(32) NOT NULL,
            previous_deployment_id UUID REFERENCES semantic_runtime_deployments(id),
            source_validation_run_id UUID,
            registry_version_number INTEGER NOT NULL,
            generator_version VARCHAR(32) NOT NULL,
            created_by VARCHAR(256),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            activated_at TIMESTAMPTZ,
            completed_at TIMESTAMPTZ,
            health_status VARCHAR(32),
            error_summary TEXT,
            manifest JSONB NOT NULL DEFAULT '{}'::jsonb
        )
        """,
        "CREATE INDEX IF NOT EXISTS ix_semantic_runtime_deployments_model ON semantic_runtime_deployments (semantic_model_id)",
        "CREATE INDEX IF NOT EXISTS ix_semantic_runtime_deployments_status ON semantic_runtime_deployments (status)",
        """
        CREATE TABLE IF NOT EXISTS semantic_runtime_state (
            semantic_model_id UUID PRIMARY KEY REFERENCES semantic_models(id) ON DELETE CASCADE,
            active_deployment_id UUID REFERENCES semantic_runtime_deployments(id),
            previous_deployment_id UUID REFERENCES semantic_runtime_deployments(id),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS semantic_runtime_events (
            id UUID PRIMARY KEY,
            deployment_id UUID NOT NULL REFERENCES semantic_runtime_deployments(id) ON DELETE CASCADE,
            event_type VARCHAR(64) NOT NULL,
            detail JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """,
        "CREATE INDEX IF NOT EXISTS ix_semantic_runtime_events_deployment ON semantic_runtime_events (deployment_id)",
    ]
    with engine.begin() as conn:
        for stmt in stmts:
            conn.execute(text(stmt))

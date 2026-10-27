"""M7A AI model registry foundation

Revision ID: m7a_ai_registry_001
Revises: c4_semantic_connection_001
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "m7a_ai_registry_001"
down_revision: Union[str, Sequence[str], None] = "c4_semantic_connection_001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ai_providers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=True),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("key", sa.String(128), nullable=False),
        sa.Column("provider_type", sa.String(32), nullable=False),
        sa.Column("base_url", sa.String(1024), nullable=True),
        sa.Column("secret_ref", sa.String(512), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("config_json", postgresql.JSONB(), nullable=True),
        sa.Column("last_test_status", sa.String(32), nullable=True),
        sa.Column("last_test_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("workspace_id", "project_id", "key", name="uq_ai_providers_workspace_project_key"),
    )
    op.create_index("ix_ai_providers_workspace_project", "ai_providers", ["workspace_id", "project_id"])
    op.create_index("ix_ai_providers_type", "ai_providers", ["provider_type"])

    op.create_table(
        "ai_models",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("provider_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("ai_providers.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=True),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("key", sa.String(128), nullable=False),
        sa.Column("model_id", sa.String(256), nullable=False),
        sa.Column("model_type", sa.String(32), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("context_window", sa.Integer(), nullable=True),
        sa.Column("max_output_tokens", sa.Integer(), nullable=True),
        sa.Column("supports_streaming", sa.Boolean(), nullable=True),
        sa.Column("supports_tools", sa.Boolean(), nullable=True),
        sa.Column("supports_json_mode", sa.Boolean(), nullable=True),
        sa.Column("supports_vision", sa.Boolean(), nullable=True),
        sa.Column("config_json", postgresql.JSONB(), nullable=True),
        sa.Column("last_test_status", sa.String(32), nullable=True),
        sa.Column("last_test_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("workspace_id", "project_id", "key", name="uq_ai_models_workspace_project_key"),
    )
    op.create_index("ix_ai_models_provider", "ai_models", ["provider_id"])
    op.create_index("ix_ai_models_type", "ai_models", ["model_type"])

    op.create_table(
        "model_assignments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=True),
        sa.Column("capability", sa.String(64), nullable=False),
        sa.Column("model_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("ai_models.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("workspace_id", "project_id", "capability", name="uq_model_assignments_scope_capability"),
    )
    op.create_index("ix_model_assignments_model", "model_assignments", ["model_id"])

    op.create_table(
        "model_test_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=True),
        sa.Column("provider_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("ai_providers.id", ondelete="SET NULL"), nullable=True),
        sa.Column("model_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("ai_models.id", ondelete="SET NULL"), nullable=True),
        sa.Column("test_type", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("safe_message", sa.Text(), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_model_test_runs_created", "model_test_runs", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_model_test_runs_created", table_name="model_test_runs")
    op.drop_table("model_test_runs")
    op.drop_index("ix_model_assignments_model", table_name="model_assignments")
    op.drop_table("model_assignments")
    op.drop_index("ix_ai_models_type", table_name="ai_models")
    op.drop_index("ix_ai_models_provider", table_name="ai_models")
    op.drop_table("ai_models")
    op.drop_index("ix_ai_providers_type", table_name="ai_providers")
    op.drop_index("ix_ai_providers_workspace_project", table_name="ai_providers")
    op.drop_table("ai_providers")

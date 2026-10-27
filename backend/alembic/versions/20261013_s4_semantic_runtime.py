"""S4 semantic runtime activation

Revision ID: s4_semantic_runtime_001
Revises: s3_semantic_gov_001
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from ddl_types import JSON, UUID, json_object_default

revision: str = "s4_semantic_runtime_001"
down_revision: Union[str, Sequence[str], None] = "s3_semantic_gov_001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "semantic_runtime_deployments",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("workspace_id", UUID, sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("project_id", UUID, sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("semantic_model_id", UUID, sa.ForeignKey("semantic_models.id", ondelete="CASCADE"), nullable=False),
        sa.Column("semantic_version_id", UUID, sa.ForeignKey("semantic_versions.id"), nullable=False),
        sa.Column("runtime_adapter", sa.String(64), nullable=False),
        sa.Column("artifact_uri", sa.Text(), nullable=False),
        sa.Column("artifact_checksum", sa.String(128), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("previous_deployment_id", UUID, sa.ForeignKey("semantic_runtime_deployments.id"), nullable=True),
        sa.Column("source_validation_run_id", UUID, nullable=True),
        sa.Column("registry_version_number", sa.Integer(), nullable=False),
        sa.Column("generator_version", sa.String(32), nullable=False),
        sa.Column("created_by", sa.String(256), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("health_status", sa.String(32), nullable=True),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column("manifest", JSON, nullable=False, server_default=json_object_default()),
    )
    op.create_index("ix_semantic_runtime_deployments_model", "semantic_runtime_deployments", ["semantic_model_id"])
    op.create_index("ix_semantic_runtime_deployments_status", "semantic_runtime_deployments", ["status"])

    op.create_table(
        "semantic_runtime_state",
        sa.Column("semantic_model_id", UUID, sa.ForeignKey("semantic_models.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("active_deployment_id", UUID, sa.ForeignKey("semantic_runtime_deployments.id"), nullable=True),
        sa.Column("previous_deployment_id", UUID, sa.ForeignKey("semantic_runtime_deployments.id"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    op.create_table(
        "semantic_runtime_events",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("deployment_id", UUID, sa.ForeignKey("semantic_runtime_deployments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("detail", JSON, nullable=False, server_default=json_object_default()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_semantic_runtime_events_deployment", "semantic_runtime_events", ["deployment_id"])


def downgrade() -> None:
    op.drop_index("ix_semantic_runtime_events_deployment", table_name="semantic_runtime_events")
    op.drop_table("semantic_runtime_events")
    op.drop_table("semantic_runtime_state")
    op.drop_index("ix_semantic_runtime_deployments_status", table_name="semantic_runtime_deployments")
    op.drop_index("ix_semantic_runtime_deployments_model", table_name="semantic_runtime_deployments")
    op.drop_table("semantic_runtime_deployments")

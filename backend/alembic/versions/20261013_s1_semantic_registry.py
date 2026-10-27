"""S1 semantic registry foundation

Revision ID: s1_semantic_001
Revises: m3b_skills_001
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "s1_semantic_001"
down_revision: Union[str, Sequence[str], None] = "m3b_skills_001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "semantic_models",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("key", sa.String(128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("active_version_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("project_id", "key", name="uq_semantic_models_project_key"),
    )
    op.create_index("ix_semantic_models_workspace", "semantic_models", ["workspace_id"])
    op.create_index("ix_semantic_models_project", "semantic_models", ["project_id"])

    op.create_table(
        "semantic_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "semantic_model_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("semantic_models.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("created_by", sa.String(256), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("runtime_adapter", sa.String(64), nullable=True),
        sa.Column("runtime_artifact_uri", sa.Text(), nullable=True),
        sa.Column("runtime_artifact_checksum", sa.String(128), nullable=True),
        sa.Column("runtime_artifact_version", sa.String(64), nullable=True),
        sa.UniqueConstraint("semantic_model_id", "version_number", name="uq_semantic_versions_model_version"),
    )
    op.create_index("ix_semantic_versions_model", "semantic_versions", ["semantic_model_id"])
    op.create_index("ix_semantic_versions_status", "semantic_versions", ["status"])

    op.create_foreign_key(
        "fk_semantic_models_active_version",
        "semantic_models",
        "semantic_versions",
        ["active_version_id"],
        ["id"],
        ondelete="SET NULL",
        use_alter=True,
    )

    for table, cols in (
        (
            "semantic_entities",
            [
                sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
                sa.Column(
                    "semantic_version_id",
                    postgresql.UUID(as_uuid=True),
                    sa.ForeignKey("semantic_versions.id", ondelete="CASCADE"),
                    nullable=False,
                ),
                sa.Column("key", sa.String(128), nullable=False),
                sa.Column("name", sa.String(256), nullable=False),
                sa.Column("description", sa.Text(), nullable=True),
                sa.Column("source_type", sa.String(32), nullable=False),
                sa.Column("catalog", sa.String(128), nullable=True),
                sa.Column("schema", sa.String(128), nullable=True),
                sa.Column("table_name", sa.String(256), nullable=True),
                sa.Column("view_name", sa.String(256), nullable=True),
                sa.Column("primary_key", sa.String(256), nullable=True),
                sa.Column("metadata", postgresql.JSONB(), nullable=False, server_default="{}"),
            ],
        ),
        (
            "semantic_metrics",
            [
                sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
                sa.Column(
                    "semantic_version_id",
                    postgresql.UUID(as_uuid=True),
                    sa.ForeignKey("semantic_versions.id", ondelete="CASCADE"),
                    nullable=False,
                ),
                sa.Column("key", sa.String(128), nullable=False),
                sa.Column("name", sa.String(256), nullable=False),
                sa.Column("description", sa.Text(), nullable=True),
                sa.Column("business_definition", sa.Text(), nullable=True),
                sa.Column("expression", sa.Text(), nullable=False),
                sa.Column("aggregation", sa.String(32), nullable=True),
                sa.Column("source_entity_key", sa.String(128), nullable=False),
                sa.Column("format", sa.String(64), nullable=True),
                sa.Column("unit", sa.String(64), nullable=True),
                sa.Column("synonyms", postgresql.JSONB(), nullable=False, server_default="[]"),
                sa.Column("metadata", postgresql.JSONB(), nullable=False, server_default="{}"),
            ],
        ),
        (
            "semantic_dimensions",
            [
                sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
                sa.Column(
                    "semantic_version_id",
                    postgresql.UUID(as_uuid=True),
                    sa.ForeignKey("semantic_versions.id", ondelete="CASCADE"),
                    nullable=False,
                ),
                sa.Column("key", sa.String(128), nullable=False),
                sa.Column("name", sa.String(256), nullable=False),
                sa.Column("description", sa.Text(), nullable=True),
                sa.Column("source_entity_key", sa.String(128), nullable=False),
                sa.Column("source_column", sa.String(256), nullable=False),
                sa.Column("data_type", sa.String(64), nullable=True),
                sa.Column("synonyms", postgresql.JSONB(), nullable=False, server_default="[]"),
                sa.Column("metadata", postgresql.JSONB(), nullable=False, server_default="{}"),
            ],
        ),
        (
            "semantic_relationships",
            [
                sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
                sa.Column(
                    "semantic_version_id",
                    postgresql.UUID(as_uuid=True),
                    sa.ForeignKey("semantic_versions.id", ondelete="CASCADE"),
                    nullable=False,
                ),
                sa.Column("key", sa.String(128), nullable=False),
                sa.Column("name", sa.String(256), nullable=False),
                sa.Column("from_entity_key", sa.String(128), nullable=False),
                sa.Column("to_entity_key", sa.String(128), nullable=False),
                sa.Column("relationship_type", sa.String(32), nullable=False),
                sa.Column("join_type", sa.String(32), nullable=False),
                sa.Column("join_expression", sa.Text(), nullable=False),
                sa.Column("description", sa.Text(), nullable=True),
                sa.Column("metadata", postgresql.JSONB(), nullable=False, server_default="{}"),
            ],
        ),
        (
            "semantic_terms",
            [
                sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
                sa.Column(
                    "semantic_version_id",
                    postgresql.UUID(as_uuid=True),
                    sa.ForeignKey("semantic_versions.id", ondelete="CASCADE"),
                    nullable=False,
                ),
                sa.Column("key", sa.String(128), nullable=False),
                sa.Column("term", sa.String(256), nullable=False),
                sa.Column("definition", sa.Text(), nullable=True),
                sa.Column("synonyms", postgresql.JSONB(), nullable=False, server_default="[]"),
                sa.Column("related_metric_keys", postgresql.JSONB(), nullable=False, server_default="[]"),
                sa.Column("related_dimension_keys", postgresql.JSONB(), nullable=False, server_default="[]"),
                sa.Column("related_entity_keys", postgresql.JSONB(), nullable=False, server_default="[]"),
                sa.Column("metadata", postgresql.JSONB(), nullable=False, server_default="{}"),
            ],
        ),
    ):
        op.create_table(table, *cols)
        op.create_index(f"ix_{table}_version", table, ["semantic_version_id"])
        op.create_unique_constraint(f"uq_{table}_version_key", table, ["semantic_version_id", "key"])


def downgrade() -> None:
    for table in (
        "semantic_terms",
        "semantic_relationships",
        "semantic_dimensions",
        "semantic_metrics",
        "semantic_entities",
    ):
        op.drop_table(table)
    op.drop_constraint("fk_semantic_models_active_version", "semantic_models", type_="foreignkey")
    op.drop_table("semantic_versions")
    op.drop_table("semantic_models")

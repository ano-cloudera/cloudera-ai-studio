"""S1 semantic registry foundation

Revision ID: s1_semantic_001
Revises: m3b_skills_001
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from ddl_types import JSON, UUID, create_foreign_key, drop_foreign_key, json_array_default, json_object_default

revision: str = "s1_semantic_001"
down_revision: Union[str, Sequence[str], None] = "m3b_skills_001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "semantic_models",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("workspace_id", UUID, sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("project_id", UUID, sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("key", sa.String(128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("active_version_id", UUID, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("project_id", "key", name="uq_semantic_models_project_key"),
    )
    op.create_index("ix_semantic_models_workspace", "semantic_models", ["workspace_id"])
    op.create_index("ix_semantic_models_project", "semantic_models", ["project_id"])

    op.create_table(
        "semantic_versions",
        sa.Column("id", UUID, primary_key=True),
        sa.Column(
            "semantic_model_id",
            UUID,
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

    create_foreign_key(
        "fk_semantic_models_active_version",
        "semantic_models",
        "semantic_versions",
        ["active_version_id"],
        ["id"],
        ondelete="SET NULL",
    )

    for table, cols in (
        (
            "semantic_entities",
            [
                sa.Column("id", UUID, primary_key=True),
                sa.Column(
                    "semantic_version_id",
                    UUID,
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
                sa.Column("metadata", JSON, nullable=False, server_default=json_object_default()),
            ],
        ),
        (
            "semantic_metrics",
            [
                sa.Column("id", UUID, primary_key=True),
                sa.Column(
                    "semantic_version_id",
                    UUID,
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
                sa.Column("synonyms", JSON, nullable=False, server_default=json_array_default()),
                sa.Column("metadata", JSON, nullable=False, server_default=json_object_default()),
            ],
        ),
        (
            "semantic_dimensions",
            [
                sa.Column("id", UUID, primary_key=True),
                sa.Column(
                    "semantic_version_id",
                    UUID,
                    sa.ForeignKey("semantic_versions.id", ondelete="CASCADE"),
                    nullable=False,
                ),
                sa.Column("key", sa.String(128), nullable=False),
                sa.Column("name", sa.String(256), nullable=False),
                sa.Column("description", sa.Text(), nullable=True),
                sa.Column("source_entity_key", sa.String(128), nullable=False),
                sa.Column("source_column", sa.String(256), nullable=False),
                sa.Column("data_type", sa.String(64), nullable=True),
                sa.Column("synonyms", JSON, nullable=False, server_default=json_array_default()),
                sa.Column("metadata", JSON, nullable=False, server_default=json_object_default()),
            ],
        ),
        (
            "semantic_relationships",
            [
                sa.Column("id", UUID, primary_key=True),
                sa.Column(
                    "semantic_version_id",
                    UUID,
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
                sa.Column("metadata", JSON, nullable=False, server_default=json_object_default()),
            ],
        ),
        (
            "semantic_terms",
            [
                sa.Column("id", UUID, primary_key=True),
                sa.Column(
                    "semantic_version_id",
                    UUID,
                    sa.ForeignKey("semantic_versions.id", ondelete="CASCADE"),
                    nullable=False,
                ),
                sa.Column("key", sa.String(128), nullable=False),
                sa.Column("term", sa.String(256), nullable=False),
                sa.Column("definition", sa.Text(), nullable=True),
                sa.Column("synonyms", JSON, nullable=False, server_default=json_array_default()),
                sa.Column("related_metric_keys", JSON, nullable=False, server_default=json_array_default()),
                sa.Column("related_dimension_keys", JSON, nullable=False, server_default=json_array_default()),
                sa.Column("related_entity_keys", JSON, nullable=False, server_default=json_array_default()),
                sa.Column("metadata", JSON, nullable=False, server_default=json_object_default()),
            ],
        ),
    ):
        op.create_table(
            table,
            *cols,
            sa.UniqueConstraint("semantic_version_id", "key", name=f"uq_{table}_version_key"),
        )
        op.create_index(f"ix_{table}_version", table, ["semantic_version_id"])


def downgrade() -> None:
    for table in (
        "semantic_terms",
        "semantic_relationships",
        "semantic_dimensions",
        "semantic_metrics",
        "semantic_entities",
    ):
        op.drop_table(table)
    drop_foreign_key("fk_semantic_models_active_version", "semantic_models")
    op.drop_table("semantic_versions")
    op.drop_table("semantic_models")

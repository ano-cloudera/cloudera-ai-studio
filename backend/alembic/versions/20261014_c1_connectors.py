"""C1 connector registry

Revision ID: c1_connectors_001
Revises: s4_semantic_runtime_001
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from ddl_types import JSON, UUID, json_object_default

revision: str = "c1_connectors_001"
down_revision: Union[str, Sequence[str], None] = "s4_semantic_runtime_001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "connectors",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("workspace_id", UUID, sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("project_id", UUID, sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("key", sa.String(128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("connector_type", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("config", JSON, nullable=False, server_default=json_object_default()),
        sa.Column("secret_ref", sa.String(512), nullable=True),
        sa.Column("created_by", sa.String(256), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("last_tested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_test_status", sa.String(32), nullable=True),
        sa.Column("last_test_message", sa.Text(), nullable=True),
        sa.Column("metadata", JSON, nullable=False, server_default=json_object_default()),
        sa.UniqueConstraint(
            "workspace_id",
            "project_id",
            "key",
            name="uq_connectors_workspace_project_key",
        ),
    )
    op.create_index("ix_connectors_workspace_project", "connectors", ["workspace_id", "project_id"])
    op.create_index("ix_connectors_type", "connectors", ["connector_type"])
    op.create_index("ix_connectors_status", "connectors", ["status"])
    op.create_index("ix_connectors_enabled", "connectors", ["enabled"])


def downgrade() -> None:
    op.drop_constraint("uq_connectors_workspace_project_key", "connectors", type_="unique")
    op.drop_index("ix_connectors_enabled", table_name="connectors")
    op.drop_index("ix_connectors_status", table_name="connectors")
    op.drop_index("ix_connectors_type", table_name="connectors")
    op.drop_index("ix_connectors_workspace_project", table_name="connectors")
    op.drop_table("connectors")

"""M3A prompt management

Revision ID: m3a_prompts_001
Revises: m2b_chunks_001
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from ddl_types import JSON, UUID, create_foreign_key, drop_foreign_key

revision: str = "m3a_prompts_001"
down_revision: Union[str, Sequence[str], None] = "m2b_chunks_001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "prompts",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("workspace_id", UUID, sa.ForeignKey("workspaces.id"), nullable=True),
        sa.Column("project_id", UUID, sa.ForeignKey("projects.id"), nullable=True),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("key", sa.String(128), nullable=False),
        sa.Column("scope", sa.String(32), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("active_version_id", UUID, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_prompts_key", "prompts", ["key"])
    op.create_index("ix_prompts_scope", "prompts", ["scope"])
    op.create_index("ix_prompts_workspace", "prompts", ["workspace_id"])
    op.create_index("ix_prompts_project", "prompts", ["project_id"])

    op.create_table(
        "prompt_versions",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("prompt_id", UUID, sa.ForeignKey("prompts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("created_by", sa.String(256), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("prompt_id", "version_number", name="uq_prompt_versions_prompt_version"),
    )
    op.create_index("ix_prompt_versions_prompt", "prompt_versions", ["prompt_id"])
    op.create_index("ix_prompt_versions_status", "prompt_versions", ["status"])

    create_foreign_key(
        "fk_prompts_active_version",
        "prompts",
        "prompt_versions",
        ["active_version_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    drop_foreign_key("fk_prompts_active_version", "prompts")
    op.drop_table("prompt_versions")
    op.drop_table("prompts")

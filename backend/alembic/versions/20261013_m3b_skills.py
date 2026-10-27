"""M3B skills management

Revision ID: m3b_skills_001
Revises: m3a_prompts_001
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from ddl_types import JSON, UUID, create_foreign_key, drop_foreign_key, json_array_default, json_object_default

revision: str = "m3b_skills_001"
down_revision: Union[str, Sequence[str], None] = "m3a_prompts_001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "skills",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("workspace_id", UUID, sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("project_id", UUID, sa.ForeignKey("projects.id"), nullable=True),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("key", sa.String(128), nullable=False),
        sa.Column("scope", sa.String(32), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("active_version_id", UUID, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_skills_key", "skills", ["key"])
    op.create_index("ix_skills_scope", "skills", ["scope"])
    op.create_index("ix_skills_workspace", "skills", ["workspace_id"])
    op.create_index("ix_skills_project", "skills", ["project_id"])

    op.create_table(
        "skill_versions",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("skill_id", UUID, sa.ForeignKey("skills.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("instructions", sa.Text(), nullable=False, server_default=""),
        sa.Column("prompt_key", sa.String(128), nullable=True),
        sa.Column("input_schema", JSON, nullable=True),
        sa.Column("output_schema", JSON, nullable=True),
        sa.Column("allowed_tools", JSON, nullable=False, server_default=json_array_default()),
        sa.Column("config", JSON, nullable=False, server_default=json_object_default()),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("skill_id", "version_number", name="uq_skill_versions_skill_version"),
    )
    op.create_index("ix_skill_versions_skill", "skill_versions", ["skill_id"])
    op.create_index("ix_skill_versions_status", "skill_versions", ["status"])

    create_foreign_key(
        "fk_skills_active_version",
        "skills",
        "skill_versions",
        ["active_version_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    drop_foreign_key("fk_skills_active_version", "skills")
    op.drop_table("skill_versions")
    op.drop_table("skills")

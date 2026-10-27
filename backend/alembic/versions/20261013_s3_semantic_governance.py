"""S3 semantic governance validation history

Revision ID: s3_semantic_gov_001
Revises: s1_semantic_001
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from ddl_types import JSON, UUID, json_object_default

revision: str = "s3_semantic_gov_001"
down_revision: Union[str, Sequence[str], None] = "s1_semantic_001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("semantic_versions", sa.Column("last_validation_run_id", UUID, nullable=True))
    op.add_column("semantic_versions", sa.Column("activation_readiness", sa.String(32), nullable=True))
    op.add_column("semantic_versions", sa.Column("validated_at", sa.DateTime(timezone=True), nullable=True))

    op.create_table(
        "semantic_validation_runs",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("semantic_version_id", UUID, sa.ForeignKey("semantic_versions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("mode", sa.String(32), nullable=False, server_default="full"),
        sa.Column("summary", JSON, nullable=False, server_default=json_object_default()),
        sa.Column("validator_version", sa.String(32), nullable=False),
        sa.Column("created_by", sa.String(256), nullable=True),
    )
    op.create_index("ix_semantic_validation_runs_version", "semantic_validation_runs", ["semantic_version_id"])

    op.create_table(
        "semantic_validation_issues",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("validation_run_id", UUID, sa.ForeignKey("semantic_validation_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("object_type", sa.String(32), nullable=True),
        sa.Column("object_key", sa.String(128), nullable=True),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("remediation", sa.Text(), nullable=True),
        sa.Column("metadata", JSON, nullable=False, server_default=json_object_default()),
    )
    op.create_index("ix_semantic_validation_issues_run", "semantic_validation_issues", ["validation_run_id"])

    op.create_table(
        "semantic_test_cases",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("semantic_version_id", UUID, sa.ForeignKey("semantic_versions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("expected_metric_keys", JSON, nullable=False, server_default=sa.text("'[]'")),
        sa.Column("expected_dimension_keys", JSON, nullable=False, server_default=sa.text("'[]'")),
        sa.Column("expected_entity_keys", JSON, nullable=False, server_default=sa.text("'[]'")),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("metadata", JSON, nullable=False, server_default=json_object_default()),
    )
    op.create_index("ix_semantic_test_cases_version", "semantic_test_cases", ["semantic_version_id"])


def downgrade() -> None:
    op.drop_index("ix_semantic_test_cases_version", table_name="semantic_test_cases")
    op.drop_table("semantic_test_cases")
    op.drop_index("ix_semantic_validation_issues_run", table_name="semantic_validation_issues")
    op.drop_table("semantic_validation_issues")
    op.drop_index("ix_semantic_validation_runs_version", table_name="semantic_validation_runs")
    op.drop_table("semantic_validation_runs")
    op.drop_column("semantic_versions", "validated_at")
    op.drop_column("semantic_versions", "activation_readiness")
    op.drop_column("semantic_versions", "last_validation_run_id")

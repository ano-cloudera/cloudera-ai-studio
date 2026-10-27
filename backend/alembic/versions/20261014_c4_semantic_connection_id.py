"""C4 semantic entity connection_id

Revision ID: c4_semantic_connection_001
Revises: c1_connectors_001
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c4_semantic_connection_001"
down_revision: Union[str, Sequence[str], None] = "c1_connectors_001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "semantic_entities",
        sa.Column("connection_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_semantic_entities_connection_id",
        "semantic_entities",
        "connectors",
        ["connection_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index("ix_semantic_entities_connection_id", "semantic_entities", ["connection_id"])


def downgrade() -> None:
    op.drop_index("ix_semantic_entities_connection_id", table_name="semantic_entities")
    op.drop_constraint("fk_semantic_entities_connection_id", "semantic_entities", type_="foreignkey")
    op.drop_column("semantic_entities", "connection_id")

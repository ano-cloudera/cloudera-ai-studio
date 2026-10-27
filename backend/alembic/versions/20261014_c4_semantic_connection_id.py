"""C4 semantic entity connection_id

Revision ID: c4_semantic_connection_001
Revises: c1_connectors_001
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from ddl_types import UUID, create_foreign_key, drop_foreign_key

revision: str = "c4_semantic_connection_001"
down_revision: Union[str, Sequence[str], None] = "c1_connectors_001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("semantic_entities") as batch:
            batch.add_column(sa.Column("connection_id", UUID, nullable=True))
            batch.create_foreign_key(
                "fk_semantic_entities_connection_id",
                "connectors",
                ["connection_id"],
                ["id"],
                ondelete="RESTRICT",
            )
            batch.create_index("ix_semantic_entities_connection_id", ["connection_id"])
    else:
        op.add_column(
            "semantic_entities",
            sa.Column("connection_id", UUID, nullable=True),
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
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("semantic_entities") as batch:
            batch.drop_index("ix_semantic_entities_connection_id")
            batch.drop_constraint("fk_semantic_entities_connection_id", type_="foreignkey")
            batch.drop_column("connection_id")
    else:
        op.drop_index("ix_semantic_entities_connection_id", table_name="semantic_entities")
        drop_foreign_key("fk_semantic_entities_connection_id", "semantic_entities")
        op.drop_column("semantic_entities", "connection_id")

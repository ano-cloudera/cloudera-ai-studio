"""Shared Alembic column types (PostgreSQL + SQLite)."""

from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

UUID = sa.Uuid()
JSON = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def json_object_default() -> sa.TextClause:
    return sa.text("'{}'")


def json_array_default() -> sa.TextClause:
    return sa.text("'[]'")


def _is_sqlite() -> bool:
    bind = op.get_bind()
    return bind.dialect.name == "sqlite"


def create_foreign_key(
    constraint_name: str,
    source_table: str,
    referent_table: str,
    local_cols: Sequence[str],
    remote_cols: Sequence[str],
    **kwargs,
) -> None:
    if _is_sqlite():
        with op.batch_alter_table(source_table) as batch:
            batch.create_foreign_key(
                constraint_name,
                referent_table,
                local_cols,
                remote_cols,
                **kwargs,
            )
    else:
        op.create_foreign_key(
            constraint_name,
            source_table,
            referent_table,
            local_cols,
            remote_cols,
            **kwargs,
        )


def drop_foreign_key(constraint_name: str, source_table: str, **kwargs) -> None:
    if _is_sqlite():
        with op.batch_alter_table(source_table) as batch:
            batch.drop_constraint(constraint_name, type_="foreignkey")
    else:
        op.drop_constraint(constraint_name, source_table, type_="foreignkey", **kwargs)

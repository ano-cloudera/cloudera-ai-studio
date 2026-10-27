"""M2B document chunks

Revision ID: m2b_chunks_001
Revises: m2a_documents_001
Create Date: 2026-10-13

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "m2b_chunks_001"
down_revision: Union[str, Sequence[str], None] = "m2a_documents_001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "document_chunks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("library_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("libraries.id"), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("section", sa.String(512), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=True),
        sa.Column("vector_id", sa.String(64), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_document_chunks_document", "document_chunks", ["document_id", "chunk_index"])
    op.create_index("ix_document_chunks_library", "document_chunks", ["library_id"])


def downgrade() -> None:
    op.drop_index("ix_document_chunks_library", table_name="document_chunks")
    op.drop_index("ix_document_chunks_document", table_name="document_chunks")
    op.drop_table("document_chunks")

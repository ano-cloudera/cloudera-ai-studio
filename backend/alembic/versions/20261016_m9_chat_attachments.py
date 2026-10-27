"""M9 chat attachments metadata

Revision ID: m9_chat_attachments_001
Revises: m7a_ai_registry_001
Create Date: 2026-10-16
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "m9_chat_attachments_001"
down_revision = "m7a_ai_registry_001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "chat_attachments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("session_id", sa.String(128), nullable=False),
        sa.Column("filename", sa.String(512), nullable=False),
        sa.Column("display_name", sa.String(512), nullable=False),
        sa.Column("mime_type", sa.String(128), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("storage_path", sa.String(1024), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("documents.id"), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("processing_type", sa.String(32), nullable=False, server_default="unstructured"),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_chat_attachments_project_session", "chat_attachments", ["project_id", "session_id"])


def downgrade() -> None:
    op.drop_index("ix_chat_attachments_project_session", table_name="chat_attachments")
    op.drop_table("chat_attachments")

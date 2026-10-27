"""TTL cleanup for temporary chat attachments."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.chat.attachments.constants import ATTACHMENT_STATUS_EXPIRED
from app.core.config import Settings
from app.db.platform_models import ChatAttachmentRow
from app.services.chat_attachment_service import ChatAttachmentService

logger = logging.getLogger(__name__)


def cleanup_expired_attachments(
    settings: Settings,
    session: Session,
    *,
    project_id: uuid.UUID | None = None,
    limit: int = 200,
) -> dict:
    """Delete expired temporary attachments (metadata, blob, vectors). Skips promoted saves."""
    now = datetime.now(timezone.utc)
    stmt = select(ChatAttachmentRow).where(ChatAttachmentRow.expires_at <= now).limit(limit)
    if project_id:
        stmt = stmt.where(ChatAttachmentRow.project_id == project_id)
    rows = session.execute(stmt).scalars().all()
    service = ChatAttachmentService(settings, session)
    deleted = 0
    skipped = 0
    for row in rows:
        meta = row.metadata_json or {}
        if meta.get("saved_document_id"):
            row.status = ATTACHMENT_STATUS_EXPIRED
            session.add(row)
            skipped += 1
            continue
        try:
            service.delete_attachment(row.id, project_id=row.project_id)
            deleted += 1
        except Exception:
            logger.exception("attachment cleanup failed id=%s", row.id)
    session.commit()
    return {"deleted": deleted, "skipped_promoted": skipped, "scanned": len(rows)}

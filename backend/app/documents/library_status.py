from __future__ import annotations

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.db.platform_models import DocumentRow


PROCESSING_STATUSES = frozenset({"UPLOADED", "QUEUED", "PROCESSING"})


def library_lifecycle_status(*, document_count: int, failed_count: int, processing_count: int) -> str:
    if document_count == 0:
        return "ready"
    if failed_count > 0:
        return "attention"
    if processing_count > 0:
        return "processing"
    return "ready"


def document_status_counts(session: Session, library_ids: list) -> dict:
    if not library_ids:
        return {}
    rows = session.execute(
        select(
            DocumentRow.library_id,
            func.count(DocumentRow.id),
            func.sum(case((DocumentRow.status == "FAILED", 1), else_=0)),
            func.sum(
                case(
                    (DocumentRow.status.in_(tuple(PROCESSING_STATUSES)), 1),
                    else_=0,
                )
            ),
        )
        .where(DocumentRow.library_id.in_(library_ids))
        .group_by(DocumentRow.library_id)
    ).all()
    out: dict = {}
    for library_id, total, failed, processing in rows:
        out[library_id] = {
            "document_count": int(total or 0),
            "failed_count": int(failed or 0),
            "processing_count": int(processing or 0),
        }
    return out

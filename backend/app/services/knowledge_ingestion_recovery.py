"""Startup recovery for interrupted Knowledge document ingestion (single-backend)."""
from __future__ import annotations

import logging
import threading
import uuid
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.platform_engine import get_session_factory
from app.db.platform_models import DocumentRow
from app.jobs.document_runner import _run_document_ingestion
from app.services.document_service import DocumentService, DocumentServiceError
from app.storage.object_store import build_object_store
from app.vectors.store import build_vector_store

logger = logging.getLogger(__name__)

RECOVERABLE_STATUSES = frozenset({"QUEUED", "PROCESSING"})
MAX_STARTUP_RECOVERY_ATTEMPTS = 5
_RECOVERY_THREADS: list[threading.Thread] = []


def _is_chat_attachment_document(row: DocumentRow) -> bool:
    meta = row.metadata_json or {}
    return meta.get("source_type") == "chat_attachment"


def find_recoverable_documents(session: Session) -> list[DocumentRow]:
    rows = session.scalars(
        select(DocumentRow).where(DocumentRow.status.in_(tuple(RECOVERABLE_STATUSES)))
    ).all()
    return [row for row in rows if not _is_chat_attachment_document(row)]


def _increment_recovery_attempt(row: DocumentRow) -> int:
    meta = dict(row.metadata_json or {})
    count = int(meta.get("recovery_attempts") or 0) + 1
    meta["recovery_attempts"] = count
    row.metadata_json = meta
    return count


def prepare_document_for_recovery(
    settings: Settings,
    session: Session,
    row: DocumentRow,
    *,
    store=None,
) -> bool:
    """Mark row QUEUED when recoverable; return True if ingestion should be enqueued."""
    object_store = store or build_object_store(settings.document_storage_root)
    if not object_store.exists(row.storage_path):
        meta = dict(row.metadata_json or {})
        meta["error_summary"] = "storage_missing"
        row.status = "FAILED"
        row.metadata_json = meta
        session.add(row)
        session.commit()
        logger.warning("knowledge_recovery_failed document_id=%s reason=storage_missing", row.id)
        return False

    attempts = _increment_recovery_attempt(row)
    if attempts > MAX_STARTUP_RECOVERY_ATTEMPTS:
        meta = dict(row.metadata_json or {})
        meta["error_summary"] = "recovery_limit_exceeded"
        row.status = "FAILED"
        row.metadata_json = meta
        session.add(row)
        session.commit()
        logger.warning(
            "knowledge_recovery_failed document_id=%s reason=recovery_limit attempts=%s",
            row.id,
            attempts,
        )
        return False

    try:
        DocumentService(settings, session).queue_reprocess(row.id)
    except DocumentServiceError as exc:
        logger.warning("knowledge_recovery_skip document_id=%s code=%s", row.id, exc.code)
        return False
    logger.info("knowledge_recovery_requeue document_id=%s attempt=%s", row.id, attempts)
    return True


def scan_and_enqueue_startup_recovery(settings: Settings) -> int:
    """Requeue interrupted Knowledge documents after backend restart. Returns enqueue count."""
    vector_store = build_vector_store(settings)
    if vector_store is None:
        logger.info("knowledge_recovery_scan skipped reason=qdrant_unavailable")
        return 0

    factory = get_session_factory(settings.database_url)
    to_run: list[uuid.UUID] = []
    with factory() as session:
        candidates = find_recoverable_documents(session)
        logger.info("knowledge_recovery_scan candidates=%s", len(candidates))
        store = build_object_store(settings.document_storage_root)
        for row in candidates:
            if prepare_document_for_recovery(settings, session, row, store=store):
                to_run.append(row.id)

    for document_id in to_run:
        thread = threading.Thread(
            target=_run_document_ingestion,
            args=(settings, document_id),
            name=f"knowledge-recovery-{document_id.hex[:8]}",
            daemon=True,
        )
        thread.start()
        _RECOVERY_THREADS.append(thread)

    if to_run:
        logger.info("knowledge_recovery_enqueued count=%s", len(to_run))
    return len(to_run)


def recovery_threads_for_tests() -> Iterable[threading.Thread]:
    return tuple(_RECOVERY_THREADS)

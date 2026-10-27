from __future__ import annotations

import logging
import threading
import uuid
from typing import Protocol, runtime_checkable

from fastapi import BackgroundTasks

from app.core.config import Settings
from app.db.platform_engine import get_session_factory
from app.services.ingestion_pipeline import IngestionPipeline

logger = logging.getLogger(__name__)

_INGESTION_SLOTS = threading.Semaphore(3)


def ingestion_concurrency_limit() -> int:
    return 3


@runtime_checkable
class DocumentJobRunner(Protocol):
    def enqueue(self, background_tasks: BackgroundTasks, document_id: uuid.UUID) -> None: ...


def _run_document_ingestion(settings: Settings, document_id: uuid.UUID) -> None:
    with _INGESTION_SLOTS:
        factory = get_session_factory(settings.database_url)
        with factory() as session:
            try:
                IngestionPipeline(settings, session).process(document_id)
            except Exception:
                logger.exception("background ingestion failed document_id=%s", document_id)


class BackgroundTaskDocumentJobRunner:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def enqueue(self, background_tasks: BackgroundTasks, document_id: uuid.UUID) -> None:
        background_tasks.add_task(_run_document_ingestion, self._settings, document_id)


def build_document_job_runner(settings: Settings) -> DocumentJobRunner:
    return BackgroundTaskDocumentJobRunner(settings)

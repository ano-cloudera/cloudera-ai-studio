from __future__ import annotations

import logging
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.platform_models import DocumentChunkRow, DocumentRow
from app.documents.chunker import TokenChunker
from app.documents.parser import build_document_parser, materialize_bytes_for_parse
from app.embeddings.provider import EmbeddingProvider, get_embedding_provider
from app.storage.object_store import ObjectStore, build_object_store
from app.vectors.store import VectorPoint, VectorStore, build_vector_store

logger = logging.getLogger(__name__)

STAGES = ("parse", "normalize", "chunk", "embed", "index")


class IngestionPipeline:
    def __init__(
        self,
        settings: Settings,
        session: Session,
        *,
        object_store: ObjectStore | None = None,
        embedding: EmbeddingProvider | None = None,
        vector_store: VectorStore | None = None,
    ) -> None:
        self._settings = settings
        self._session = session
        self._store = object_store or build_object_store(settings.document_storage_root)
        self._parser = build_document_parser(settings)
        self._chunker = TokenChunker(
            chunk_size_tokens=settings.document_chunk_size_tokens,
            chunk_overlap_tokens=settings.document_chunk_overlap_tokens,
        )
        self._embedding = embedding or get_embedding_provider(settings)
        self._vectors = vector_store if vector_store is not None else build_vector_store(settings)

    def _set_status(
        self,
        row: DocumentRow,
        *,
        status: str,
        stage: str | None = None,
        error_summary: str | None = None,
        extra: dict | None = None,
    ) -> None:
        meta = dict(row.metadata_json or {})
        if stage is not None:
            meta["processing_stage"] = stage
        if error_summary is not None:
            meta["error_summary"] = error_summary
        elif status == "READY":
            meta.pop("error_summary", None)
        if extra:
            meta.update(extra)
        row.status = status
        row.metadata_json = meta
        row.updated_at = datetime.now(timezone.utc)
        self._session.add(row)
        self._session.commit()

    def _clear_existing_artifacts(self, document_id: uuid.UUID) -> None:
        if self._vectors:
            self._vectors.delete_document(document_id=document_id)
        self._session.execute(delete(DocumentChunkRow).where(DocumentChunkRow.document_id == document_id))
        self._session.commit()

    def process(self, document_id: uuid.UUID) -> None:
        row = self._session.get(DocumentRow, document_id)
        if not row:
            raise ValueError(f"document not found: {document_id}")

        tmp_path: Path | None = None
        started = time.perf_counter()
        try:
            self._set_status(row, status="PROCESSING", stage="parse")
            if not self._vectors:
                raise RuntimeError("Qdrant is not configured (QDRANT_URL)")
            data = self._store.get(row.storage_path)
            suffix = Path(row.filename).suffix or ".bin"
            tmp_path = materialize_bytes_for_parse(data, suffix)
            parsed = self._parser.parse(
                path=tmp_path,
                mime_type=row.mime_type,
                document_id=row.id,
                title=row.original_filename,
            )

            self._set_status(row, status="PROCESSING", stage="normalize")
            self._clear_existing_artifacts(document_id)

            self._set_status(row, status="PROCESSING", stage="chunk")
            chunks = self._chunker.chunk(
                parsed,
                workspace_id=row.workspace_id,
                project_id=row.project_id,
                library_id=row.library_id,
            )
            if not chunks:
                raise RuntimeError("No text extracted from document")

            chunk_rows: list[DocumentChunkRow] = []
            now = datetime.now(timezone.utc)
            for ch in chunks:
                chunk_rows.append(
                    DocumentChunkRow(
                        id=ch.chunk_id,
                        workspace_id=ch.workspace_id,
                        project_id=ch.project_id,
                        library_id=ch.library_id,
                        document_id=ch.document_id,
                        chunk_index=ch.chunk_index,
                        page_number=ch.page_number,
                        section=ch.section,
                        text=ch.text,
                        token_count=ch.token_count,
                        vector_id=str(ch.chunk_id),
                        metadata_json=ch.metadata,
                        created_at=now,
                        updated_at=now,
                    )
                )
            self._session.add_all(chunk_rows)
            self._session.commit()

            self._set_status(row, status="PROCESSING", stage="embed")
            embed_started = time.perf_counter()
            vectors = self._embedding.embed_texts(
                [c.text for c in chunks],
                batch_size=self._settings.embedding_batch_size,
            )
            embed_ms = int((time.perf_counter() - embed_started) * 1000)

            self._set_status(row, status="PROCESSING", stage="index")
            self._vectors.ensure_collection(dimension=self._embedding.dimension)
            points = [
                VectorPoint(
                    chunk_id=ch.chunk_id,
                    vector=vec,
                    payload={
                        "workspace_id": str(ch.workspace_id),
                        "project_id": str(ch.project_id),
                        "library_id": str(ch.library_id),
                        "document_id": str(ch.document_id),
                        "chunk_id": str(ch.chunk_id),
                        "page_number": ch.page_number,
                        "section": ch.section,
                        "filename": row.original_filename,
                        "chunk_index": ch.chunk_index,
                    },
                )
                for ch, vec in zip(chunks, vectors, strict=True)
            ]
            self._vectors.upsert(points)

            total_ms = int((time.perf_counter() - started) * 1000)
            self._set_status(
                row,
                status="READY",
                stage="index",
                extra={
                    "embedding_model": self._embedding.model_name,
                    "embedding_dimension": self._embedding.dimension,
                    "embedding_ms": embed_ms,
                    "processing_ms": total_ms,
                    "chunk_count": len(chunks),
                },
            )
        except Exception as exc:
            logger.exception("document ingestion failed document_id=%s", document_id)
            safe = type(exc).__name__
            if isinstance(exc, RuntimeError):
                safe = str(exc)[:500]
            self._session.rollback()
            fresh = self._session.get(DocumentRow, document_id)
            if fresh:
                self._set_status(fresh, status="FAILED", error_summary=safe)
            raise
        finally:
            if tmp_path and tmp_path.exists():
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

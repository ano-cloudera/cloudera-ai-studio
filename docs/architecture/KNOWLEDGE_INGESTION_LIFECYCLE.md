# Knowledge ingestion lifecycle

## Upload → READY

1. **Upload** — `DocumentService.upload_document` validates file, writes blob to `document_storage_root` (persistent object store key), inserts `documents` row with `status=QUEUED`.
2. **Enqueue** — `BackgroundTaskDocumentJobRunner` (`app/jobs/document_runner.py`) schedules `IngestionPipeline.process` on FastAPI `BackgroundTasks` (in-process thread pool after response).
3. **Pipeline** (`app/services/ingestion_pipeline.py`):
   - `PROCESSING` / stage `parse` — read blob, parse (Docling or pypdf fallback)
   - `normalize` — `_clear_existing_artifacts` (delete Qdrant points + DB chunks)
   - `chunk` — token chunks → `document_chunks`
   - `embed` — embedding provider
   - `index` — Qdrant upsert (point id = `chunk_id`)
   - `READY` with `chunk_count` in metadata

Terminal states: **READY**, **FAILED** (with `error_summary` in metadata).

## Execution model

| Question | Answer |
|----------|--------|
| Queue persisted? | **YES** — `documents.status` in PostgreSQL |
| Worker persisted? | **NO** — FastAPI background tasks are process-local |
| Lost on exit? | In-flight background work; **DB status may remain `PROCESSING`/`QUEUED`** |

## Restart recovery (single backend)

On application startup (`app/main.py` lifespan, after Qdrant collection ensure):

`scan_and_enqueue_startup_recovery` (`app/services/knowledge_ingestion_recovery.py`):

- Scans `QUEUED` and `PROCESSING` Knowledge documents (excludes `metadata.source_type=chat_attachment`)
- Verifies blob exists; missing blob → **FAILED** (`storage_missing`)
- Increments `recovery_attempts`; >5 → **FAILED** (`recovery_limit_exceeded`)
- Sets **QUEUED** via `queue_reprocess`, enqueues ingestion thread (same path as upload)
- **READY** / **FAILED** are not auto-requeued

## Idempotency

Re-ingestion clears prior chunks/vectors before re-indexing (`_clear_existing_artifacts`). Qdrant upsert uses stable chunk UUIDs.

## Chat attachments

Attachments reuse `DocumentRow` with `source_type=chat_attachment` but are **excluded** from startup recovery; use attachment retry/TTL flows.

## Limitations

- No distributed queue (single backend instance assumed)
- Qdrant unavailable at startup: recovery skipped (documents stay `QUEUED`/`PROCESSING`)
- Future NFS: recovery uses storage keys only (portable)

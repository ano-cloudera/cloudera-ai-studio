# Backend CAI Application — deployment spec (neutral)

| Field | Value |
|-------|--------|
| Runtime | Python 3.10, FastAPI, uvicorn |
| Start command | `scripts/cai/start-backend.sh start` |
| Alt (container) | `python -m uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port ${PORT} --workers 1` |
| Default port | 8001 (configurable via `BACKEND_PORT` / `PORT`) |
| Workers | **Must be `1`** when `DATABASE_URL` is SQLite |
| Bind address | `0.0.0.0` (not `127.0.0.1`) |

## Persistent volumes (NFS)

| Mount | Purpose | Class |
|-------|---------|--------|
| `${CAI_DATA_DIR}/metadata/` | SQLite `studio.db` | MUST PERSIST |
| `${CAI_DATA_DIR}/documents/` | Knowledge PDFs, blobs | MUST PERSIST |
| `${CAI_DATA_DIR}/var/semantic-runtime/` | Published semantic artifacts | MUST PERSIST |
| `${CAI_DATA_DIR}/attachments/` | Chat attachments | MUST PERSIST |
| `${CAI_DATA_DIR}/exports/` | Export scratch | TEMPORARY |
| `${CAI_DATA_DIR}/logs/` | File logs (optional) | OPTIONAL |

## Health

| Endpoint | Use |
|----------|-----|
| `GET /health` | Liveness — process up |
| `GET /health/ready` | Readiness — `core_ready`; may list `feature_gaps` (e.g. `rag_needs_qdrant`) |

Qdrant outage: Backend stays up; `core_ready=true` when metadata + storage OK; RAG gap only.

## Dependencies

- Qdrant HTTP (`QDRANT_URL`) — optional for core; required for Knowledge vectors
- External LLM API — chat/RAG synthesis
- External connectors — structured Ask (PostgreSQL, Impala, Trino)

## Bootstrap (not automatic on start)

Golden Banking demo: `python scripts/demo/bootstrap_golden_banking.py --apply` with `GOLDEN_PATH_API_BASE` pointing at this Backend URL.

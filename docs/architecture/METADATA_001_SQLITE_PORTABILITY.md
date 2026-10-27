# METADATA-001 — SQLite platform metadata (local acceptance)

## Why SQLite (PoC)

- Single backend process / single worker matches file-backed metadata.
- Alembic + SQLAlchemy portable types support both **SQLite (local sim)** and **PostgreSQL (HA path)**.
- DuckDB remains **Ask Data analytics only**, not platform OLTP metadata.

## Single-process contract

- `UVICORN_WORKERS=1` (enforced in `validate_startup_config` when `DATABASE_URL` is SQLite).
- Do not run multiple uvicorn workers against SQLite metadata.
- Future HA → external PostgreSQL (unchanged from CAI audit).

## Storage layout (local sim)

```text
runtime/cai-sim/
├── metadata/studio.db
├── documents/
├── semantic/
├── attachments/   (optional)
└── logs/          (optional)
```

Configure via `deployment/profiles/cai-sim-local.env` or:

- `CAI_DATA_DIR`
- `DATABASE_URL=sqlite+pysqlite:///…/metadata/studio.db`
- `DOCUMENT_STORAGE_ROOT`, `SEMANTIC_RUNTIME_STORAGE_ROOT`

## SQLAlchemy portability

- `app/db/types.py`: `PlatformJSON`, `PlatformUUID`
- `app/db/platform_engine.py`: `foreign_keys=ON`, `busy_timeout=30000`, `journal_mode=DELETE`, `synchronous=NORMAL`, `check_same_thread=False`

## API / readiness

- `/api/v1/*` requires configured `DATABASE_URL` (Postgres **or** SQLite), not `STATE_STORE=postgres`.
- Readiness exposes `metadata_database` (and legacy `postgres` key with same payload).

## Rollback to PostgreSQL

1. Point `DATABASE_URL` back to `postgresql+psycopg://…`
2. Run `alembic upgrade head` on Postgres
3. Keep document/semantic paths or repoint storage roots

No code rollback required — dual dialect is native.

## Tests

- `tests/test_metadata_sqlite_portability.py` — Alembic bootstrap, FK pragma, session + concurrent usage
- Full suite: **433 passed** (see `testing/evidence/metadata-001/post-migration/SUMMARY.md`)

## Related

- [LOCAL_CAI_SIMULATION.md](../deployment/LOCAL_CAI_SIMULATION.md)
- [CAI_DEPLOYMENT_ENV_CONTRACT.md](./CAI_DEPLOYMENT_ENV_CONTRACT.md)

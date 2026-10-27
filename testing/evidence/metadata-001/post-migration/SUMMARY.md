# METADATA-001 post-migration evidence

## Backend tests

```
433 passed, 85 skipped, 10 deselected
```

Includes `tests/test_metadata_sqlite_portability.py` (Alembic bootstrap, FK pragma, conversation + concurrent usage writes).

## Fresh SQLite Alembic

Path: `runtime/cai-sim-test-fresh/metadata/studio.db`

Command:

```bash
DATABASE_URL="sqlite+pysqlite:////…/runtime/cai-sim-test-fresh/metadata/studio.db" \
  .venv/bin/alembic -c backend/alembic.ini upgrade head
```

Result: **PASS** (all revisions through `m9_chat_attachments_001`).

## PostgreSQL Alembic regression

Dev Postgres `DATABASE_URL` from `.env`: **current = head** (`m9_chat_attachments_001`).

## Frontend

- Vitest: **225 passed**
- `npm run build`: **PASS** (see CI log in local run)

## Local CAI sim startup

```bash
./scripts/dev-cai-sim-backend.sh start
```

Uses `runtime/cai-sim/metadata/studio.db`, `UVICORN_WORKERS=1`.

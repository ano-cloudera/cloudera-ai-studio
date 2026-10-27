# Local CAI simulation (SQLite metadata)

Local-only METADATA-001 workflow. **Not** a CAI deployment.

## Prerequisites

- Repo venv: `.venv` with backend deps
- Local Qdrant on `6333` (for Knowledge/RAG)
- Banking PostgreSQL connector credentials in root `.env` (external data source — unchanged)

## 1. Qdrant

Use your existing local Qdrant process (same as dev stack).

## 2. Backend (SQLite metadata)

```bash
./scripts/dev-cai-sim-backend.sh start
./scripts/dev-cai-sim-backend.sh status
```

First start runs `alembic upgrade head` on:

`runtime/cai-sim/metadata/studio.db`

## 3. Frontend

```bash
./scripts/dev-frontend.sh start
```

Ensure `BACKEND_API_URL=http://127.0.0.1:8001` (default).

## Health

```bash
curl -s http://127.0.0.1:8001/health | jq .
curl -s http://127.0.0.1:8001/health/ready | jq '.core_ready, .components.metadata_database'
```

Expect `metadata_database.dialect=sqlite` and `core_ready=true` when storage paths are writable.

## Golden Banking on CAI sim

1. Bootstrap connector + knowledge on **SQLite platform DB** (same scripts as Postgres path, with CAI sim backend env):

```bash
set -a && source deployment/profiles/cai-sim-local.env && set +a
# re-export DATABASE_URL after sourcing (see dev-cai-sim-backend.sh)
python scripts/demo/register_banking_knowledge.py   # when backend up
```

2. Run gates (backend must be on `:8001`):

```bash
python scripts/demo/golden_path_banking_phase1_gate.py
python scripts/demo/golden_path_banking_phase2_knowledge_gate.py
```

## Restart persistence check

1. Create chat / prompt / knowledge artifact via UI
2. `./scripts/dev-cai-sim-backend.sh stop && ./scripts/dev-cai-sim-backend.sh start`
3. Confirm records and document blobs under `runtime/cai-sim/`

## Fresh install (disposable path)

```bash
rm -rf runtime/cai-sim-disposable
CAI_DATA_DIR=runtime/cai-sim-disposable DATABASE_URL= \
  ./scripts/dev-cai-sim-backend.sh start
```

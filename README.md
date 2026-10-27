# Cloudera AI Studio

Standalone application workspace: Ask Data, Semantic Layer, Knowledge (RAG), Data Sources, Prompts, Skills, and AI Model Registry.

## Prerequisites

- Python 3.10+
- Node.js 20+ (see `.nvmrc`)
- PostgreSQL (recommended for full platform features) or sqlite for limited local mode

## Quick start

```bash
./scripts/bootstrap/bootstrap-local.sh   # creates .venv, installs deps, optional migrations
cp .env.example .env                     # edit DATABASE_URL and API keys
./scripts/dev-backend.sh start
./scripts/dev-frontend.sh                # http://127.0.0.1:3001
```

Backend API: `http://127.0.0.1:8001` — lifecycle: `./scripts/dev-backend.sh status|restart|stop|logs`

Combined stack: `./scripts/dev-stack.sh` (backend in background, frontend in foreground)

## Database

When `STATE_STORE=postgres` and `DATABASE_URL` is set:

```bash
./scripts/migration/upgrade-db.sh
cd backend && ../.venv/bin/alembic current && ../.venv/bin/alembic heads
```

## Tests

```bash
make test-backend
make test-frontend
make build
```

Live semantic gates (backend must be running):

```bash
cd backend && PYTHONPATH=. ../.venv/bin/python scripts/sem_p2b_live_gate.py
```

## Layout

| Path | Purpose |
|------|---------|
| `backend/` | FastAPI application, Alembic, pytest, live gate scripts |
| `frontend/` | Next.js UI (port 3001) |
| `deployment/profiles/` | Profile env snippets |
| `config/` | Example env templates |
| `scripts/` | Lifecycle and bootstrap |
| `docs/` | Operations and feature docs |
| `testing/` | Live/browser evidence output (optional) |

## Environment

See `.env.example` and `config/examples/accelerator.env.example`. Never commit `.env`.

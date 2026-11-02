# Local development

Requires Python 3.10+, Node.js 20+ (`.nvmrc`), and optionally Docker for Qdrant and Postgres.

```bash
./scripts/bootstrap/bootstrap-local.sh   # creates .venv and installs dependencies
cp .env.example .env                     # then edit DATABASE_URL and keys; never commit .env
./scripts/dev-backend.sh start           # http://127.0.0.1:8001
./scripts/dev-frontend.sh                # http://127.0.0.1:3001
```

```bash
make test-backend     # pytest (SQLite, no Docker needed)
make test-frontend    # vitest
make build            # production build of the frontend
```

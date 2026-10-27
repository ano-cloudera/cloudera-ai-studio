# Operations runbook

## Local backend lifecycle (port 8001)

Use the canonical launcher — **do not** start backend with ad-hoc `nohup uvicorn` or `pkill uvicorn`.

```bash
./scripts/dev-backend.sh start    # idempotent; ALREADY_RUNNING if healthy
./scripts/dev-backend.sh status   # PID + port + /health + /health/ready
./scripts/dev-backend.sh restart
./scripts/dev-backend.sh stop     # only stops PID in .tmp/backend-8001.pid
./scripts/dev-backend.sh logs     # tail -f .tmp/backend-8001.log
```

Environment loads `deployment/profiles/runtime-closure.env`, then optional repo `.env`.  
`PYTHONPATH=backend` and `CORS_ORIGINS` for frontend `:3001` are applied by the script.

UAT/SIT may override semantic model for a run (not baked into the launcher):

```bash
SEMANTIC_DEFAULT_MODEL_KEY=uat_commercial_p2_20261016 ./scripts/dev-backend.sh restart
```

Full stack: `DEV_DATA_BACKEND=duckdb ./scripts/run-dev-stack.sh` (backend via `backend.sh`).

## Backend unhealthy

1. Check logs for startup error (`DATABASE_URL`, import failures).
2. `curl -s http://<backend>/health/ready | jq`
3. Run `python scripts/doctor.py` on the host.

## PostgreSQL unavailable

- Symptom: `STATE_STORE=postgres` and `/health/ready` → `postgres.not_ready`
- Verify network, credentials, `DATABASE_URL` (platform DB only).
- Re-run `bash scripts/migration/upgrade-db.sh`.

## Qdrant unavailable

- RAG ingestion/search fails; Ask Data unaffected if connectors/legacy datasource configured.
- Set `FEATURE_PROFILE=ASK_DATA_ONLY` if RAG not needed.
- Verify `QDRANT_URL` and collection.

## LLM unavailable

- Ask Data/RAG return user-facing errors; configure `GEMINI_API_KEY` / Qwen / OpenAI-compatible URL.
- Dev: use providers that report `available` in `/models`.

## Connector failing

- Connector Manager → Test connection.
- Check `env://` secret refs and network to Impala/Trino/Postgres **business** host (not platform `DATABASE_URL`).

## Semantic runtime rollback

- Semantic Layer UI → Runtime → rollback to previous deployment.
- Verify `SEMANTIC_RUNTIME_STORAGE_ROOT` mounted and writable.

## Migration issues

- `cd backend && alembic current`
- `bash scripts/migration/upgrade-db.sh`
- Never auto-downgrade.

## Document ingestion failure

- Check `DOCUMENT_STORAGE_ROOT` permissions and disk space.
- Verify embedding provider and Qdrant for RAG pipeline.

## Frontend cannot reach API

- Verify `NEXT_PUBLIC_BACKEND_URL` matches deployed backend.
- CORS: `CORS_ORIGINS` includes frontend origin.

## Next.js stale `.next` / missing chunk (dev)

- Symptom: `Cannot find module './611.js'`, `ChunkLoadError`, or `MODULE_NOT_FOUND` after `npm run build` while `next dev` is still on port **3001**.
- Cause: production build and dev server both writing `.next` concurrently.
- Rule: **never** run `npm run build` while dev is active on 3001. Use `npm run build:safe` in `frontend/`.
- Recovery:

  ```bash
  cd frontend
  rm -rf .next
  npm run dev -- -p 3001
  ```

- SIT pre-flight (full clean build + dev + route checks):

  ```bash
  ./scripts/frontend-preflight.sh
  ```

- Check port 3001: `lsof -nP -iTCP:3001 -sTCP:LISTEN`
- Full stack uses safe frontend start via `scripts/run-dev-stack.sh` → `frontend-clean-dev.sh --skip-build --detach`.

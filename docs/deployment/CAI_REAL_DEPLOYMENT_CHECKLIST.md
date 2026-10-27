# Real CAI deployment validation checklist

Execute on **actual Cloudera AI** infrastructure (not local dev).

## Application startup

- [ ] Qdrant CAI Application starts; persistent volume mounted
- [ ] Backend CAI Application starts (`UVICORN_WORKERS=1`)
- [ ] Frontend CAI Application starts (production `next start`, not dev)
- [ ] Backend NFS writable (`CAI_DATA_DIR`)
- [ ] SQLite `metadata/studio.db` persists across Backend restart
- [ ] Qdrant storage persists across Qdrant restart

## Networking

- [ ] Frontend → Backend (`BACKEND_API_URL` / rewrites)
- [ ] Backend → Qdrant (`QDRANT_URL`)
- [ ] Backend → external Banking PostgreSQL (connector)
- [ ] CORS: Frontend origin in `CORS_ORIGINS`

## Secrets

- [ ] LLM provider keys in CAI secret store (not in Git/SQLite)
- [ ] Connector `env://` refs resolve (e.g. `BANKING_DEMO_PG_PASSWORD`)
- [ ] AI Model Registry stores references only

## Health

- [ ] Backend liveness: `/health`
- [ ] Backend readiness: `/health/ready` with Qdrant up
- [ ] Backend readiness with Qdrant down: `core_ready=true`, `rag_needs_qdrant` gap
- [ ] Frontend liveness: `GET /`
- [ ] Qdrant health endpoint confirmed for deployed Qdrant version

## Golden demo

- [ ] `bootstrap_golden_banking.py --apply` against deployed Backend URL
- [ ] Raw Ask, Knowledge RAG, Governed Semantic
- [ ] Prompts / Skills surfaces
- [ ] Restart Backend — no reseed required
- [ ] Restart Qdrant — Knowledge retrieval works
- [ ] Restart Frontend — UI loads
- [ ] Full stack restart
- [ ] Clean install on empty NFS volume

## Sign-off

- [ ] `CAI_3_APP_DEPLOYMENT_READINESS_PASS` artifacts reviewed
- [ ] AMP packaging can proceed

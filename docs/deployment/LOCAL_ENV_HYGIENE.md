# Local environment hygiene (Cloudera AI Studio)

Single reference for **which env files matter**, **default ports**, and **what never gets committed**.

## Canonical layout

| File | Role |
|------|------|
| **Repo root `.env`** | **Primary** for local backend (`scripts/dev-backend.sh` sources it). Put backend secrets and `DATABASE_URL` here. |
| **`frontend/.env.local`** | Next.js dev/build overrides (proxy target, feature flags). Public `NEXT_PUBLIC_*` only — **no API keys**. |
| **`.env.example`** (root) | Legacy monolith template; prefer **`backend/.env.example`** + **`frontend/.env.example`** for new setups. |
| **`backend/.env.example`** | Backend variable catalog (AMP-aligned). |
| **`frontend/.env.example`** | Frontend public flags + `BACKEND_API_URL` for proxy. |
| **`deployment/profiles/cai.env.example`** | CAI 3/4-app split — **no secrets**, copy into Application env. |
| **`deployment/profiles/runtime-closure.env`** | Optional local overlay (gitignored). |

## Default dev stack

| Service | URL |
|---------|-----|
| Backend | `http://127.0.0.1:8001` |
| Frontend | `http://127.0.0.1:3001` |

```bash
./scripts/dev-up.sh             # backend + frontend (:3001)
# Frontend 500 or blank? (jangan build saat dev jalan):
./scripts/dev-frontend.sh restart-clean
```

Backend auto-defaults `CORS_ORIGINS` to `3001` if unset (`scripts/lib/backend-common.sh`).

## Required for full product locally

| Variable | Why |
|----------|-----|
| `DATABASE_URL` or default sqlite | Platform metadata, workspace settings (Ask Data, **MCP**), chat sessions |
| `QDRANT_URL` | Knowledge RAG |
| At least one LLM key **or** `LLM_MODE=mock` | Chat (non-MCP paths) |
| `BACKEND_API_URL` / `frontend/.env.local` | Next proxy `/api` → backend |

## MCP-specific

| Where | What |
|-------|------|
| **Backend env** | `BRAVE_API_KEY` (and any other names referenced in Settings → MCP) |
| **Workspace DB** | Server display name, transport, command/URL, **env var names only** |
| **Not in frontend** | MCP secrets never in `NEXT_PUBLIC_*` |

Configure in UI: **Settings → MCP** → preset → **Test connection** → **Save MCP connections**.

## Hygiene rules

1. **Never commit** `.env`, `.env.local`, `frontend/.env.local`, or `runtime-closure.env`.
2. **Never put secrets** in workspace JSON, MCP settings API payloads, or frontend env.
3. **One source of truth locally:** root `.env` for backend; avoid duplicating the same keys in three files unless documented.
4. After pulling MCP/settings changes: **restart backend** so new routes load; restart frontend if proxy target changed.
5. Pre-deploy smoke: `python3 scripts/demo/verify_pre_deploy.py http://127.0.0.1:8001` → `"ok": true`.

## Sync checklist (when adding a new env var)

1. `backend/app/core/config.py` (if Settings field)
2. `backend/.env.example`
3. `deployment/profiles/cai.env.example` (if CAI-relevant)
4. `docs/architecture/CAI_DEPLOYMENT_ENV_CONTRACT.md`

## Related

- [CAI_4_APP_DEPLOY_RUNBOOK.md](./CAI_4_APP_DEPLOY_RUNBOOK.md)
- [CAI_DEPLOYMENT_ENV_CONTRACT.md](../architecture/CAI_DEPLOYMENT_ENV_CONTRACT.md)
- [PROJECT_STATE.md](../../PROJECT_STATE.md)

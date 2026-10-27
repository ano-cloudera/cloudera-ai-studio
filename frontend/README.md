# Cloudera AI Studio — Frontend (`frontend`)

User-facing branding defaults to **Cloudera AI Studio** / **AI Studio** via `src/config/appConfig.ts` and `NEXT_PUBLIC_*` overrides.

Next.js client for **Ask Data**, **Knowledge (M2)**, Usage, and Settings. This is the **accelerator UI** — not the legacy `frontend/` tree on port 3000.

## Run locally (M2 Knowledge included)

**Recommended:** full dev stack (backend **8001**, UI **3001**):

```bash
./scripts/dev-backend.sh start   # canonical API (survives shell exit)
./scripts/run-dev-stack.sh       # or: backend + frontend together
# Web: http://127.0.0.1:3001/knowledge
```

Or manually:

```bash
cd frontend
cp .env.example .env.local   # ensure NEXT_PUBLIC_FEATURE_DOCUMENTS=true
npm ci
npm run dev:safe -- -p 3001   # or: bash scripts/frontend-clean-dev.sh --skip-build
```

### SIT pre-flight (recommended)

Never run `npm run build` while `next dev` is on port **3001** — it can leave stale `.next` chunks (`Cannot find module './611.js'`).

```bash
./scripts/frontend-preflight.sh
# or: cd frontend && npm run preflight
```

Sequence: stop scoped dev → `rm -rf .next` → `npm run build` → start dev → route/proxy checks → two restart cycles.

Safe production build only:

```bash
npm run build:safe
```

Recovery:

```bash
cd frontend
rm -rf .next
npm run dev -- -p 3001
```

Point `BACKEND_API_URL` at **backend** with `STATE_STORE=postgres` for Knowledge/RAG APIs.

**After changing `next.config.mjs` rewrites, restart `next dev`.** Verify proxy:

```bash
./scripts/proxy-route-gate.sh http://127.0.0.1:3001/api
```

## Why Knowledge might not appear

| Cause | Fix |
|--------|-----|
| Running **`frontend/`** on :3000 (legacy Tempo UI) | Use **`frontend/`** on :3001 |
| `NEXT_PUBLIC_FEATURE_DOCUMENTS=false` | Set `true` in `.env.local`; **restart** `next dev` |
| Stale `.next` after flag change | `rm -rf .next && npm run dev` |
| Backend not on postgres | Knowledge APIs return 503 |

Sidebar order: **Ask Data → Knowledge → Usage → Settings** (when flags enabled).

## Tests

```bash
npm test
npm run build
```

## Cloudera AI Application

Deploy this app (`frontend`) with backend. Entrypoint pattern: see repo root README.

Browser calls same-origin `/api/*`; `next.config.mjs` proxies to `BACKEND_API_URL`.

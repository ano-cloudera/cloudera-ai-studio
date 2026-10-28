# CAI 3-App deployment readiness

> **Superseded for CAI Applications:** the Script field must be a Python entrypoint (`deployment/cai/launchers/studio-*/app.py`), never a `.sh` file. `scripts/cai/start-*.sh` are for local/Session use only. See [CAI_4_APP_DEPLOY_RUNBOOK.md](./CAI_4_APP_DEPLOY_RUNBOOK.md).

**Milestone:** `CAI_3_APP_DEPLOYMENT_READINESS`  
**Status:** Local readiness only — **no CAI deploy, no AMP package** in this milestone.

## Target topology

```
User → Frontend CAI App → Backend CAI App (1 worker)
                              ├─ SQLite metadata on NFS (${CAI_DATA_DIR}/metadata/studio.db)
                              ├─ documents / semantic runtime on NFS
                              ├─ Qdrant CAI App (QDRANT_URL)
                              ├─ external PostgreSQL / Impala / Trino (connectors)
                              └─ external LLM + embedding providers
Qdrant CAI App → persistent Qdrant storage volume
```

Related: [CAI deployment env contract](../architecture/CAI_DEPLOYMENT_ENV_CONTRACT.md), [CAI PoC limitations](./CAI_POC_LIMITATIONS.md), [Real CAI checklist](./CAI_REAL_DEPLOYMENT_CHECKLIST.md).

---

## Runtime inventory

| Component | Version / command |
|-----------|-------------------|
| Python | 3.10 (`.python-version`) |
| Node | LTS (see `frontend/package.json`; Next 15) |
| Backend deps | `backend/requirements.txt` |
| Frontend deps | `frontend/package.json` |
| Backend start | `scripts/cai/start-backend.sh start` |
| Frontend build/start | `npm run build` → `scripts/cai/start-frontend.sh start` |
| Qdrant | Official Qdrant image / service; port **6333** |
| Backend port | `BACKEND_PORT` / `PORT` (default 8001) |
| Frontend port | `PORT` (default 3000) |

## Persistent layout (`CAI_DATA_DIR`)

```
${CAI_DATA_DIR}/
├── metadata/studio.db      MUST PERSIST
├── documents/              MUST PERSIST
├── attachments/            MUST PERSIST
├── var/semantic-runtime/   MUST PERSIST
├── exports/                TEMPORARY
└── logs/                   OPTIONAL (prefer stdout on CAI)
```

Initialize: `scripts/cai/init-storage.sh`

Local NFS emulation: `scripts/cai/nfs-local-emulation.sh` (under `/tmp/cai-nfs-sim/…` — **not** real NFS).

---

## Application contracts

| App | Spec |
|-----|------|
| Frontend | [deployment/specs/frontend-cai-application.md](../../deployment/specs/frontend-cai-application.md) |
| Backend | [deployment/specs/backend-cai-application.md](../../deployment/specs/backend-cai-application.md) |
| Qdrant | [deployment/specs/qdrant-cai-application.md](../../deployment/specs/qdrant-cai-application.md) |

### Frontend

- **Production:** `npm run build` + `next start -H 0.0.0.0`
- **Env:** `BACKEND_API_URL` (server proxy), `NEXT_PUBLIC_BACKEND_URL` (client)
- No Qdrant or metadata DB access

### Backend

- **Production:** uvicorn `app.main:app`, `--host 0.0.0.0`, `--workers 1`
- **Env:** see [deployment/profiles/cai.env.example](../../deployment/profiles/cai.env.example)
- Startup: migrate (Alembic) → optional `CAI_PLATFORM_SEED=1` → serve
- **Does not** auto-run Golden Banking bootstrap

### Qdrant

- Independent lifecycle; Backend uses `QDRANT_URL` / optional `QDRANT_API_KEY`
- Health: **`GET /healthz`** (confirm for deployed Qdrant version — **DEFERRED_TO_REAL_CAI** for final URL)

---

## Networking (no localhost in CAI)

| Link | Variable |
|------|----------|
| FE → BE | `BACKEND_API_URL` |
| BE → Qdrant | `QDRANT_URL` |
| Browser → BE | CORS via `CORS_ORIGINS` |

Code defaults (`127.0.0.1:8001` in `next.config.mjs`) are **dev fallbacks** only; CAI must set env.

---

## Secrets

| Class | Examples | Storage |
|-------|----------|---------|
| PUBLIC CONFIG | `QDRANT_URL`, `CORS_ORIGINS`, `CAI_DATA_DIR` | CAI env |
| PRIVATE CONFIG | `DATABASE_URL` (non-secret in SQLite path) | CAI env |
| SECRET | `GEMINI_API_KEY`, `OPENAI_API_KEY`, `QDRANT_API_KEY`, `BANKING_DEMO_PG_PASSWORD` | CAI secret store |

Connector / AI registry: `env://VAR_NAME` references in DB — never store raw secrets in SQLite.

---

## Health behavior

| Endpoint | Role |
|----------|------|
| `GET /health` | Liveness |
| `GET /health/ready` | Readiness; `core_ready` when metadata + storage OK |

When Qdrant is down: Backend remains alive; `feature_gaps` may include `rag_needs_qdrant`; non-RAG features continue (`backend/app/platform/readiness.py`).

---

## Embeddings & LLM

| Capability | Where |
|------------|--------|
| Embeddings | Backend `EMBEDDING_PROVIDER` / `EMBEDDING_MODEL` |
| Vectors | Qdrant (storage only) |
| Raw Ask / Semantic chat | LLM provider (registry / env) |
| Knowledge synthesis | LLM + RAG retrieval |
| Prompt / Skill | LLM via existing services |

Local Qwen or other endpoints: configure as external URL + secret — **not deployed in this milestone**.

---

## Golden demo on CAI

After Backend deploy:

```bash
export GOLDEN_PATH_API_BASE=https://<backend-service>
export BANKING_DEMO_PG_PASSWORD=<secret>
python scripts/demo/bootstrap_golden_banking.py --apply
python scripts/demo/bootstrap_golden_banking.py --validate
```

Reset (library + connector only): `reset_golden_banking.py` with `GOLDEN_RESET_CONFIRM=1`.

---

## Resource sizing (PoC estimates)

| App | CPU | RAM | GPU | Storage |
|-----|-----|-----|-----|---------|
| Frontend | 0.5–1 | 512Mi–1Gi | none | none |
| Backend | 2–4 | 4–8 Gi | none | NFS 10–50 Gi |
| Qdrant | 1–2 | 2–4 Gi | none | 5–20 Gi |

## Storage sizing (PoC starting point)

| Area | Estimate |
|------|----------|
| SQLite metadata | &lt; 500 Mi (demo) |
| PDFs + attachments | 1–5 Gi |
| Semantic artifacts | &lt; 1 Gi |
| Qdrant vectors | 1–5 Gi |
| Headroom | 2× for growth |

---

## Local validation

```bash
bash scripts/cai/nfs-local-emulation.sh
set -a && source .tmp/cai-nfs-sim.env && set +a
bash scripts/cai/start-backend.sh start
BACKEND_API_URL=http://127.0.0.1:8010 PORT=3010 bash scripts/cai/start-frontend.sh start
python scripts/cai/preflight.py
python scripts/cai/cai_3_app_deployment_readiness_gate.py
```

Evidence: `testing/evidence/cai-3-app-deployment-readiness/`

---

## Startup order

1. Qdrant (persistent volume)
2. Backend (may start before Qdrant; RAG gap until Qdrant up)
3. Frontend

---

## SQLite backup (PoC)

1. Stop Backend (single writer)
2. Copy `${CAI_DATA_DIR}/metadata/studio.db`
3. Copy `documents/`, `var/semantic-runtime/`
4. Snapshot Qdrant storage volume

---

## Logging

- Prefer **stdout/stderr** for CAI log aggregation
- Avoid unbounded logs on NFS; rotate if file logs enabled under `${CAI_DATA_DIR}/logs/`

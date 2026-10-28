# CAI 4-Application deploy runbook (hackathon)

Deploy **Cloudera AI Studio** as four Cloudera AI Applications, aligned with BNI CAI training layout (`bni-cai-technical-training/deployments/cai`).

| # | Application | Launcher | Health |
|---|-------------|----------|--------|
| 1 | **Backend** (source: `backend/`) | `deployment/cai/launchers/studio-backend/app.py` | `GET /health` |
| 2 | **Frontend** (source: `frontend/`) | `deployment/cai/launchers/studio-frontend/app.py` | `GET /` |
| 3 | **Qdrant** (+ UI) | `deployment/cai/launchers/studio-qdrant/app.py` | `GET /readyz`; UI on **CDSW_READONLY_PORT** |
| 4 | **vLLM** | `deployment/cai/launchers/studio-vllm/app.py` | `GET /health` |

Folder map: [deployment/README.md](../../deployment/README.md)

Manifest template: [deployment/cai/manifests/applications.yaml](../../deployment/cai/manifests/applications.yaml)

Per-app env templates: [deployment/cai/env/](../../deployment/cai/env/)

## Pre-deploy (Session, once)

```bash
# Repo on CAI workspace
cd cloudera-ai-studio
bash scripts/bootstrap/bootstrap-local.sh   # or equivalent venv on Session

# Qdrant binary (Application cannot download)
bash scripts/cai/prepare_qdrant_binary.sh /home/cdsw/tools/qdrant/qdrant

# Frontend production build (optional if CAI_SKIP_FRONTEND_BUILD=0 on first start)
cd frontend && npm ci && npm run build
```

## Deploy order

1. **Qdrant** — set `QDRANT_BINARY`, `QDRANT_STORAGE_PATH`, enable **readonly port** for UI.
2. **vLLM** — set `MODEL_PATH`, GPU runtime; note public/internal URL.
3. **Backend** — NFS `CAI_DATA_DIR`, `QDRANT_URL`, `CORS_ORIGINS`, LLM (`OPENAI_API_BASE` → vLLM or Gemini secret).
4. **Frontend** — `BACKEND_API_URL` (internal), `NEXT_PUBLIC_BACKEND_URL` (browser).

## Post-deploy bootstrap (Backend Session)

```bash
export GOLDEN_PATH_API_BASE=https://cai-studio-backend.<your-domain>
python3 scripts/demo/bootstrap_golden_banking.py --apply
python3 scripts/demo/apply_accelerator_demo_profile.py
```

## MCP (@ chip)

1. **Backend secret:** e.g. `BRAVE_API_KEY` on Backend CAI Application.
2. **Settings → MCP** tab → **Add Brave Search preset** → **Test connection** → **Save MCP connections**.
3. Ask Data: `@` → **Brave Search MCP** → web search question.

Uses standard **MCP protocol** (stdio/SSE via Python `mcp` SDK). Legacy `MCP_CONNECTORS_JSON` env is fallback only when no workspace servers are configured.

## Architecture checklist (demo)

| Layer | Proof |
|-------|--------|
| Trino / connectors | Connector health + governed SQL |
| OSSIE semantic | Publish + no-`@` KPI |
| Qdrant RAG | `@` library + sources |
| LangGraph | Backend logs `ask_data_route=ossie` |
| MCP | `@MCP` + `strategy=mcp` response |

## PuppyGraph

**Not required** for deploy or semantic visibility. Optional `PUPPYGRAPH_*` env only for future graph narrative.

## Pre-deploy verification (local)

```bash
./scripts/dev-backend.sh start
python3 scripts/demo/verify_pre_deploy.py
```

Pass criteria: `"ok": true` (MCP settings, connectors, live `@` MCP chat, core MCP pytest).  
`amp_readiness` may WARN on `bootstrap_validate` until banking bootstrap is run on target env.

## Deployment agenda (today)

| Step | Owner | Done when |
|------|--------|-----------|
| 1 | Infra | NFS volume mounted; 4 CAI Applications created from manifest |
| 2 | Qdrant | `/readyz` OK; readonly UI lists collections |
| 3 | vLLM | `/health` OK; `curl /v1/models` returns `studio-llm` |
| 4 | Backend | `/health/ready` `core_ready`; bootstrap + profile applied |
| 5 | Frontend | Loads Ask Data; CORS OK |
| 6 | MCP smoke | `@` Studio Demo MCP → JSON stack summary |
| 7 | Demo script | KPI no-`@` → `@` library → `@` MCP (optional) |

## Related

- [CAI_REAL_DEPLOYMENT_CHECKLIST.md](./CAI_REAL_DEPLOYMENT_CHECKLIST.md)
- [deployment/profiles/cai.env.example](../../deployment/profiles/cai.env.example)
- [AMP_MULTI_CONTEXT_POLICY.md](./AMP_MULTI_CONTEXT_POLICY.md)

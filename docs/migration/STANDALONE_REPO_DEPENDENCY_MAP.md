# Standalone repo dependency map

Extracted from `enterprise-ai-poc` → `cloudera-ai-studio` (copy-only; source repo unchanged).

| Existing path | Used by | Classification | Migrate? | New path | Notes |
|---|---|---|---|---|---|
| `backend-dev/` | FastAPI app, tests, gates | REQUIRED | Yes | `backend/` | Renamed; core product |
| `frontend-dev/` | Next.js UI | REQUIRED | Yes | `frontend/` | Renamed |
| `deployment/profiles/` | Backend lifecycle env | REQUIRED | Yes | `deployment/profiles/` | No secrets committed |
| `config/` | Bootstrap templates | REQUIRED | Yes | `config/` | |
| `scripts/bootstrap`, `migration`, lifecycle | Local dev | REQUIRED | Yes | `scripts/` | `dev-backend.sh` replaces `backend-dev.sh` |
| `assets/` | Branding (optional UI) | OPTIONAL | Yes | `assets/` | Small static set |
| `docs/backend`, `operations`, `frontend` | Runbooks | OPTIONAL | Yes | `docs/` | Trimmed; no SIT evidence bulk |
| `.env.example`, `.nvmrc`, `.python-version` | Bootstrap | REQUIRED | Yes | repo root | Real `.env` excluded |
| `backend/` (legacy) | Old Tempo stack :8000 | LEGACY | No | — | Superseded by `backend/` copy |
| `frontend/` (legacy) | Old UI :3000 | LEGACY | No | — | |
| `backend-test/` | Old tests | LEGACY | No | — | |
| `litellm/`, `model-serving/`, `neo4j-cai/` | Optional infra | OPTIONAL | No | — | Env-driven; not runtime dependency |
| `datasets/`, `reference/`, `runtime/`, `projects/` | Demo/tempo data | LEGACY/OPTIONAL | No | — | DuckDB/Impala optional via env |
| `skills/` (root) | Unrelated to app skills API | LEGACY | No | — | App skills live in backend |
| `.venv`, `node_modules`, `.next`, `.tmp` | Generated | GENERATED | No | — | Recreate locally |
| `.env` | Secrets | SECRET/LOCAL | No | — | Use `.env.example` |

Runtime code resolves `BACKEND_ROOT` / `REPO_ROOT` via pathlib (`backend/app/core/config.py`); no hard dependency on old repo name when layout is `backend/` at repo root.

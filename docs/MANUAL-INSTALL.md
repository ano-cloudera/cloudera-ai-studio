# Manual installation on Cloudera AI

The AMP in the [README](../README.md) does all of this for you. Use this page only to understand what the AMP creates, or to install by hand.

The app runs as **four Cloudera AI Applications** (Qdrant, Backend, Frontend, and an optional vLLM)
that share one project filesystem. Everything that needs a terminal is prepared once from a **Session**,
because an Application has no terminal and cannot download files.

## 0. Prerequisites

- A Cloudera AI workspace with a project and a Session runtime of **Python 3.10** (JupyterLab).
- A Trino endpoint (for example a Cloudera Data Warehouse Trino Virtual Warehouse) with write access to one schema, for loading the demo tables. The demo uses catalog `hive`, schema `default`.
- One LLM credential: a Gemini, OpenAI or Anthropic API key (as a CAI secret), or a vLLM endpoint.
- Outbound internet from the **Session** (PyPI, npm, Hugging Face, GitHub). Applications do not need it.

## 1. Get the code into the project

Create the project from this Git repository (or clone it in a Session terminal):

```bash
cd /home/cdsw
git clone https://github.infra.cloudera.com/triano/anywhere-ai-studio.git
cd anywhere-ai-studio
```

The Applications locate the repo through `STUDIO_REPO_ROOT=/home/cdsw/anywhere-ai-studio`.
Later code changes are applied with `git pull` followed by an Application **Restart**.

## 2. Prepare the tools (Session terminal, once)

```bash
cd /home/cdsw/anywhere-ai-studio

# Node.js (Sessions and Applications ship without it)
bash scripts/cai/prepare_node.sh /home/cdsw/tools/node
export PATH=/home/cdsw/tools/node/bin:$PATH

# One Python venv for the Backend (and one for vLLM if you use it)
bash scripts/cai/prepare_venvs.sh backend

# Qdrant binary and its web UI
bash scripts/cai/prepare_qdrant_binary.sh /home/cdsw/tools/qdrant/qdrant
bash scripts/cai/prepare_qdrant_ui.sh /home/cdsw/tools/qdrant/static

# Embedding model for RAG (about 2.3 GB, uses the backend venv)
bash scripts/cai/prepare_embedding_model.sh /home/cdsw/models/bge-m3

# Persistent data root shared by Session and Applications
mkdir -p /home/cdsw/cai-studio-data/{metadata,documents,var,qdrant/storage}
```

> `npm: command not found` in a new terminal means `/home/cdsw/tools/node/bin` is not on `PATH`. Re-run the `export` line.

## 3. Create the Applications

Create the Applications in this order and confirm each one before starting the next.
The manifest `deployment/cai/manifests/applications.yaml` lists the exact script, resources and health path.
Environment templates are in `deployment/cai/env/`.

| # | Application | Script | Health check |
|---|---|---|---|
| 1 | `cai-studio-qdrant` | `deployment/cai/launchers/studio-qdrant/app.py` | `/readyz` (UI at `/dashboard`) |
| 2 | `cai-studio-backend` | `deployment/cai/launchers/studio-backend/app.py` | `/health`, `/health/ready` |
| 3 | `cai-studio-frontend` | `deployment/cai/launchers/studio-frontend/app.py` | `/` |
| 4 | `cai-studio-vllm` (optional, GPU) | `deployment/cai/launchers/studio-vllm/app.py` | `/health` |

Rules that matter on Cloudera AI:

- The **Script** field must be a Python file (never a shell script). Do not set `CDSW_APP_PORT`.
- An Application starts in `/home/cdsw`, so use absolute paths and set `STUDIO_REPO_ROOT`.
- Run the Backend as **one replica, one worker** (metadata lives in SQLite on the project filesystem).
- Store secrets as CAI secrets or environment variables. The UI only stores a pointer such as `env://GEMINI_API_KEY`.

Common settings for every Application: **Runtime** JupyterLab, Python 3.10, Standard edition (vLLM uses the NVIDIA GPU edition);
**Authentication** *authenticated* (users sign in with their Cloudera AI account).
Replace `<...-app-domain>` with the domain CAI assigns to each Application after you create it
(`https://<subdomain>.<workspace-domain>`), so create Qdrant first and fill the later URLs in as you go.

### 3.1 Qdrant (vector database)

| Setting | Value |
|---|---|
| Name / Subdomain | `cai-studio-qdrant` |
| Script | `deployment/cai/launchers/studio-qdrant/app.py` |
| Resources | 4 vCPU, 8 GB, 0 GPU |

| Environment variable | Value | Change it? |
|---|---|---|
| `QDRANT_BINARY` | `/home/cdsw/tools/qdrant/qdrant` | Only if you installed the binary elsewhere in step 2 |
| `QDRANT_STORAGE_PATH` | `/home/cdsw/cai-studio-data/qdrant/storage` | Only if you changed the data root |
| `QDRANT_STATIC_DIR` | `/home/cdsw/tools/qdrant/static` | Only if you installed the UI elsewhere |
| `STUDIO_REPO_ROOT` | `/home/cdsw/anywhere-ai-studio` | **Yes**, if the repo path differs |
| `APP_STARTUP_TIMEOUT_MINUTES` | `5` | No |
| `QDRANT_API_KEY` | *(unset)* | Optional. If set, set the same value on the Backend |

Do **not** set `CDSW_APP_PORT`, `CDSW_PUBLIC_PORT` or `CDSW_READONLY_PORT`; CAI assigns them.
**Verify:** `<qdrant-app-domain>/readyz` returns OK and `<qdrant-app-domain>/dashboard` opens the Qdrant UI.

### 3.2 Backend (FastAPI)

| Setting | Value |
|---|---|
| Name / Subdomain | `cai-studio-backend` |
| Script | `deployment/cai/launchers/studio-backend/app.py` |
| Resources | 4 vCPU, 8 GB, 0 GPU, **1 replica** |

| Environment variable | Value | Change it? |
|---|---|---|
| `DEPLOYMENT_PROFILE` | `cai` | No |
| `STATE_STORE` | `sqlite` | No |
| `UVICORN_WORKERS` | `1` | No (SQLite on the project filesystem needs one worker) |
| `CAI_DATA_DIR` | `/home/cdsw/cai-studio-data` | Only if you changed the data root |
| `DATABASE_URL` | `sqlite+pysqlite:////home/cdsw/cai-studio-data/metadata/studio.db` | Only if you changed the data root |
| `DOCUMENT_STORAGE_ROOT` | `/home/cdsw/cai-studio-data/documents` | Only if you changed the data root |
| `SEMANTIC_RUNTIME_STORAGE_ROOT` | `/home/cdsw/cai-studio-data/var/semantic-runtime` | Only if you changed the data root |
| `QDRANT_URL` | `https://<qdrant-app-domain>:443` | **Yes**. Keep `:443`; never use a pod IP |
| `QDRANT_COLLECTION` | `accelerator_chunks` | No |
| `CORS_ORIGINS` | `https://<frontend-app-domain>` | **Yes** (comma-separate more than one origin, no wildcard) |
| `EMBEDDING_PROVIDER` | `bge_m3` | No |
| `EMBEDDING_MODEL` | `/home/cdsw/models/bge-m3` | Only if you downloaded the model elsewhere |
| `HF_HUB_OFFLINE` | `1` | No |
| `PYTHON_EXECUTABLE` | `/home/cdsw/.venvs/studio-backend/bin/python` | Only if the venv is elsewhere |
| `STUDIO_REPO_ROOT` | `/home/cdsw/anywhere-ai-studio` | **Yes**, if the repo path differs |
| `APP_STARTUP_TIMEOUT_MINUTES` | `10` | No |
| `GEMINI_API_KEY` or `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` | your key | **Yes**: set only the provider(s) you will use, as a **secret** |
| `TRINO_PASSWORD` | your Trino password | **Yes**, as a **secret** (referenced from the UI as `env://TRINO_PASSWORD`) |
| `QDRANT_API_KEY` | same as Qdrant | Only if you set it on Qdrant |

Do **not** set `DEFAULT_LLM_PROVIDER`: provider, model and capability assignment are chosen in the UI (Settings → AI Models).
Adding a new secret later needs a Backend restart.
**Verify:** `<backend-app-domain>/health` returns OK and `<backend-app-domain>/health/ready` reports `core_ready`.

### 3.3 Frontend (Next.js)

Next.js bakes `BACKEND_API_URL` and every `NEXT_PUBLIC_*` value into the **build**, so build from the Session first,
with the same values you will give the Application:

```bash
export PATH=/home/cdsw/tools/node/bin:$PATH
export BACKEND_API_URL=https://<backend-app-domain>
# Also export the NEXT_PUBLIC_* branding values listed below
cd /home/cdsw/anywhere-ai-studio/frontend
npm ci
npm run build
```

If the build fails, `.next` is removed and the Application cannot start (`Could not find a production build`);
fix the error and build again.

| Setting | Value |
|---|---|
| Name / Subdomain | `cai-studio-frontend` |
| Script | `deployment/cai/launchers/studio-frontend/app.py` |
| Resources | 2 vCPU, 4 GB, 0 GPU |

| Environment variable | Value | Change it? |
|---|---|---|
| `BACKEND_API_URL` | `https://<backend-app-domain>` | **Yes**. The browser only calls the Frontend; Next.js proxies `/api` to this URL |
| `NODE_HOME` | `/home/cdsw/tools/node` | Only if Node is installed elsewhere |
| `CAI_SKIP_FRONTEND_BUILD` | `0` | No (`1` skips the automatic build when `.next` is missing) |
| `STUDIO_REPO_ROOT` | `/home/cdsw/anywhere-ai-studio` | **Yes**, if the repo path differs |
| `APP_STARTUP_TIMEOUT_MINUTES` | `15` | No |
| `NEXT_PUBLIC_PRODUCT_NAME`, `NEXT_PUBLIC_PRODUCT_SHORT_NAME`, `NEXT_PUBLIC_APP_NAME`, `NEXT_PUBLIC_APP_SUBTITLE`, `NEXT_PUBLIC_APP_TAGLINE`, `NEXT_PUBLIC_SIDEBAR_FOOTER_CAPTION` | `Anywhere AI Studio` | Optional (branding, build time) |
| `NEXT_PUBLIC_SIDEBAR_POWERED_BY` | `Powered by Anywhere Cloud` | Optional (branding, build time) |
| `NEXT_PUBLIC_PRODUCT_LOGO`, `NEXT_PUBLIC_APP_LOGO`, `NEXT_PUBLIC_EMPTY_STATE_LOGO` | `/branding/anywhere-ai-logo.png` | Optional (branding, build time) |

The branding block is also in `deployment/cai/env/studio-frontend.env.example`. After a branding change, rebuild and restart.
**Verify:** the Frontend URL loads the Ask Data page, and a question reaches the Backend (no CORS or 502 errors).

### 3.4 vLLM (optional, only to serve your own model)

Skip this if you use Gemini, OpenAI or Anthropic. Run `bash scripts/cai/prepare_venvs.sh vllm` from a GPU Session,
stop that Session (one GPU per node), then create the Application.

| Setting | Value |
|---|---|
| Name / Subdomain | `cai-studio-vllm` |
| Script | `deployment/cai/launchers/studio-vllm/app.py` |
| Runtime | NVIDIA GPU edition |
| Resources | 16 vCPU, 64 GB, **1 GPU** (keep Enabled GPU at `1` after every update) |

| Environment variable | Value | Change it? |
|---|---|---|
| `MODEL_PATH` | `/home/cdsw/models/<your-model>` | **Yes**: folder with the model weights |
| `GPU_PROFILE` | `h200` (also `l40s`, `a10g`) | **Yes**, match your GPU |
| `VLLM_MODEL` | `studio-llm` | Optional: the served model name |
| `PYTHON_EXECUTABLE` | `/home/cdsw/.venvs/studio-vllm/bin/python` | Only if the venv is elsewhere |
| `TENSOR_PARALLEL_SIZE` | `1` | Only for multi-GPU |
| `MAX_MODEL_LEN`, `GPU_MEMORY_UTILIZATION`, `MAX_NUM_SEQS` | `8192`, `0.75`, `32` (H200) | Tune per GPU: L40S `8192`/`0.82`/`16`, A10G 24 GB `4096`/`0.92`/`4` |
| `HF_HUB_OFFLINE` | `1` | No |
| `STUDIO_REPO_ROOT` | `/home/cdsw/anywhere-ai-studio` | **Yes**, if the repo path differs |
| `APP_STARTUP_TIMEOUT_MINUTES` | `15` | No |
| `VLLM_API_KEY` | *(unset)* | Optional. If set, use the same value as the key in the Backend provider |
| `VLLM_TOOL_CALL_PARSER`, `VLLM_CHAT_TEMPLATE` | *(unset)* | Only for tool-calling or chat-template fixes |

If the log shows `Available KV cache memory: -N GiB`, raise `GPU_MEMORY_UTILIZATION` or lower `MAX_MODEL_LEN` / `MAX_NUM_SEQS`.
**Verify:** `<vllm-app-domain>/health` returns OK and `/v1/models` lists `studio-llm`.
Then register it in the UI: Settings → AI Models → OpenAI-compatible provider with base URL `<vllm-app-domain>/v1`.

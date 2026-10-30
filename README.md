# Anywhere AI Studio

**Governed Credit Risk Intelligence on Cloudera AI.**
One chat workspace that answers credit-risk questions from three governed sources and shows its evidence:

| Source | What it does | Example |
|---|---|---|
| **Ask Data** | Natural language → governed SQL on Trino, using a published semantic layer (metrics, dimensions, business definitions) | "Which region has the lowest approval rate from June to August 2026?" |
| **Knowledge (RAG)** | Answers from policy PDFs with page-level citations and an *Open PDF at page* link | "When does an approval-rate gap trigger an investigation?" |
| **MCP tools** | Calls an approval-likelihood model through the Model Context Protocol (advisory only) | "Assess an applicant with credit score 640, DTI 0.40 …" |

The demo data is fully synthetic (`demo/data`, `demo/knowledge`).

```
Browser ─► Frontend (Next.js) ─► Backend (FastAPI) ─┬─► Trino            governed SQL
                                                    ├─► Qdrant           document vectors
                                                    ├─► LLM provider     Gemini / OpenAI / Anthropic / vLLM
                                                    └─► MCP server       credit-risk model (stdio)
```

## Repository layout

| Path | Purpose |
|---|---|
| `backend/` | FastAPI app, Alembic migrations, prompts, pytest suite |
| `frontend/` | Next.js UI (port 3001 locally) |
| `deployment/cai/` | Cloudera AI Application launchers, manifest and per-app env templates |
| `scripts/cai/` | One-time Session scripts (Node, venvs, Qdrant, embedding model, demo data loader) |
| `scripts/mcp/` | Credit-risk MCP server and its trained model |
| `demo/data/` | Synthetic `credit_applications.csv` (12,000 rows) and `loan_quality.csv` (8,000 rows) |
| `demo/knowledge/credit-risk/` | Four synthetic policy PDFs plus two markdown policy documents |
| `docs/` | Design notes (API, RAG, semantic registry, UX) |

---

# Deploy as an AMP (one click)

`.project-metadata.yaml` turns this repository into a Cloudera AI **Applied ML Prototype**. Importing it runs two Jobs in order
and waits for each:

| Job | What it does |
|---|---|
| `install-tools` | `scripts/amp/setup.py`: Node.js, Backend virtualenv, Qdrant and its UI, the embedding model, data folders, Frontend packages. Safe to run again |
| `deploy-applications` | `scripts/amp/deploy.py`: builds the UI, then creates (or updates and restarts) the **Qdrant, Backend and Frontend Applications** through the Cloudera AI API v2 and waits until they run. URLs between the Applications are derived from the workspace domain |

You only enter environment variables once, at import. The deploy Job copies them to the Applications that need them
(the list is in `deployment/cai/manifests/applications.yaml`, which is also where Application names, resources and settings live).

**Variables at import** (all optional at import time, but the app needs an LLM key and a data source to answer questions):
`GEMINI_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `TRINO_*`, `IMPALA_*`, `POSTGRES_PASSWORD`.
For any other secret a Data Source or MCP server needs, add the variable to the project and list its name in `AMP_FORWARD_ENV`
(comma separated); the Data Source then refers to it as `env://NAME`.

**After the import**, open the Frontend and follow [Configure the demo](#configure-the-demo-step-by-step)
(LLM, Data Source, semantic layer, knowledge, MCP).

**Redeploy** after a `git pull` or after adding a variable: run the `deploy-applications` Job again.
**Check the API access first** (read-only) from a Session: `python scripts/amp/deploy.py --check`.

Known limits:
- The Application subdomains are fixed (`anywhere-qdrant`, `anywhere-backend`, `anywhere-frontend`). If they collide in your workspace,
  set `AMP_SUBDOMAIN_PREFIX`.
- The Applications are created with authentication on. If the Backend cannot reach Qdrant, or the Frontend cannot reach the Backend,
  check the Application authentication settings first.
- The deploy Job calls the Cloudera AI REST API with the key CAI provides to Jobs (`CDSW_APIV2_KEY`). It has been tested against a
  fake client only; run `--check` and `--dry-run` first on a new workspace.

---

# Install on Cloudera AI

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
| Resources | 4 vCPU, 16 GB, 0 GPU |

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
| Resources | 4 vCPU, 16 GB, 0 GPU, **1 replica** |

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

---

# Configure the demo (step by step)

Open the Frontend Application. Everything below is done in the UI except step 2.

## 1. Choose the LLM

**Settings → AI Models** → add a provider (for example Gemini) with the key reference `env://GEMINI_API_KEY`,
add a model, and assign it to the capabilities (Ask Data, Knowledge, MCP). The UI text and answers are English;
an answer follows the language of the question.

## 2. Load the demo data into Trino (Session terminal)

```bash
cd /home/cdsw/anywhere-ai-studio
/home/cdsw/.venvs/studio-backend/bin/python -m pip install trino   # if not already present
TRINO_HOST=<host> TRINO_USER=<user> TRINO_PASSWORD=<password> \
TRINO_CATALOG=hive TRINO_SCHEMA=default \
  /home/cdsw/.venvs/studio-backend/bin/python scripts/cai/load_credit_risk_demo.py --replace
```

This creates `credit_applications` (12,000 rows) and `loan_quality` (8,000 rows) as Parquet tables.
`scripts/cai/test_trino_connection.py` checks connectivity first.

## 3. Add the Data Source

**Data Sources → New connection** → Trino: host, port `443`, HTTPS, catalog `hive`, schema `default`,
user, and the password as `env://TRINO_PASSWORD`. Run **Test connection**, then browse the tables.

## 4. Build the semantic layer

**Semantic Layer** → create one model per table (`credit_applications`, `loan_quality`):

1. Add the table as an **entity** and import its columns as **dimensions**
   (for example `region_name`, `application_channel`, `customer_segment`, `application_date`).
2. Add **metrics** with business definitions and synonyms. The demo uses:

| Metric | Expression |
|---|---|
| Approval Rate (%) | `COUNT(CASE WHEN decision_status = 'Approved' THEN 1 END) * 100.0 / COUNT(application_id)` |
| Total Applications | `COUNT(application_id)` |
| Average Decision Time (hours) | `AVG(decision_time_hours)` |
| Policy-exception approvals | `COUNT(CASE WHEN decision_status = 'Approved' AND policy_exception_flag THEN 1 END)` |

3. **Publish** the model. Publishing validates the full artifact, and only published metrics are used to answer questions.
4. **Settings → Ask Data** → pin `credit_applications` as the default model, so questions resolve to it without an `@`.

## 5. Upload the knowledge documents

**Knowledge** → create a library (for example `Credit Knowledge`) and upload the PDFs from
`demo/knowledge/credit-risk/`. Wait until each document is **Ready**. Documents are stored under
`/home/cdsw/cai-studio-data/documents` and indexed in Qdrant; deleting a document in the UI also removes its vectors and files.

## 6. Register the MCP server

**Settings → MCP** → **Add server**:

| Field | Value |
|---|---|
| Name | `Credit Risk Model` |
| Transport | `stdio` |
| Command | `/home/cdsw/.venvs/studio-backend/bin/python` |
| Arguments | `/home/cdsw/anywhere-ai-studio/scripts/mcp/credit_risk_server.py` |

Click **Test connection**; it should list `assess_application_risk`, then **Save**. See `scripts/mcp/README.md`.

---

# Run the demo

Start each part from **New chat** so no earlier context leaks in. The `@` chip decides the source:
no chip → Ask Data, `@<library>` → Knowledge, `@<MCP server>` → MCP.

**1. Ask Data** (no chip)

1. Which region has the lowest approval rate from June to August 2026?
2. Compare the approval rate by region and channel from June to August 2026.
3. What is the average decision time by channel?

**2. Knowledge** (attach `@Credit Knowledge`)

1. When does an approval-rate gap trigger an investigation?
2. Can we say Branch is slower because of manual review?
3. What are the standard approval criteria?

Click a source file or a `Page N` chip to open the PDF at that page.

**3. MCP** (attach `@Credit Risk Model`)

> Assess an applicant with credit score 640, DTI 0.40, requested 150 million, Digital, Jawa Barat.

The result is an advisory approval likelihood (about 16%, Low band) with the policy checks.
It never approves or rejects an application.

Every Ask Data answer has **Summary**, **Table** and **Query** tabs; the Query tab shows the governed definition, the executed SQL and the source table.

---

# Update, restart and troubleshoot

| Change | What to do |
|---|---|
| Backend code | `git pull`, then **Restart** the Backend |
| Frontend code | `git pull`, `npm run build` in a Session, then **Restart** the Frontend and hard-refresh the browser |
| New secret | Add it to the Application, then **Restart** (the key is read at start) |

| Symptom | Likely cause |
|---|---|
| Frontend stays down, log says `Could not find a production build` | The last `npm run build` failed; rebuild and restart |
| `npm: command not found` | `export PATH=/home/cdsw/tools/node/bin:$PATH` |
| Backend `core_ready` but no answers | No model assigned in Settings → AI Models |
| Question answered by the wrong source | Wrong chip: no chip is Ask Data, a library chip is Knowledge |
| MCP test connection fails | Check the Arguments path ends in `credit_risk_server.py` and the Command is the backend venv Python |
| Knowledge answer says it cannot answer | The question is not covered by the attached library |

---

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

## Security notes

- No secrets are stored in the repository. Credentials are referenced as `env://VAR_NAME` and read from the environment.
- `.env`, local state (`runtime/`, `backend/var/`) and test output are git-ignored.
- All demo data and documents are synthetic.
# anywhere-ai-studio

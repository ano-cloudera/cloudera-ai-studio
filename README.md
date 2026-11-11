# Anywhere AI Studio

**Governed Credit Risk Intelligence on Cloudera AI.**
One chat workspace that answers credit-risk questions from three governed sources and shows its evidence:

| Source | What it does | Example |
|---|---|---|
| **Ask Data** | Natural language → governed SQL on Trino, using a published semantic layer (metrics, dimensions, business definitions) | "Which region has the lowest approval rate from June to August 2026?" |
| **Knowledge (RAG)** | Answers from policy PDFs with page-level citations and an *Open PDF at page* link | "When does an approval-rate gap trigger an investigation?" |
| **MCP tools** | Calls an approval-likelihood model through the Model Context Protocol (advisory only) | "Assess an applicant with credit score 640, DTI 0.40 …" |

The sample data is fully synthetic (`demo/data`).

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
| `docs/` | [Demo guide](docs/DEMO-GUIDE.md), [PoC guide](docs/POC-GUIDE.md), [manual install](docs/MANUAL-INSTALL.md), [local development](docs/LOCAL-DEVELOPMENT.md), design notes |

---

# Deploy as an AMP

`.project-metadata.yaml` turns this repository into a Cloudera AI **Applied ML Prototype**. Importing it runs two Jobs in order
and waits for each:

| Job | What it does |
|---|---|
| `install-tools` | `scripts/amp/setup.py`: Node.js, Backend virtualenv, Qdrant and its UI, the embedding model, data folders, Frontend packages. Safe to run again |
| `deploy-applications` | `scripts/amp/deploy.py`: builds the UI, then creates (or updates and restarts) the **Qdrant, Backend and Frontend Applications** through the Cloudera AI API v2 and waits until they run. URLs between the Applications are derived from the workspace domain |
| `update-from-github` | `scripts/amp/update.py`: `git pull --ff-only`, then redeploys when something new came in. Not run at import. Use it instead of a Session for every code update |

## Before you start

1. **Allow unauthenticated Applications.** Ask the workspace admin to enable **Site Administration -> Security -> Allow applications
   to be configured with unauthenticated access**. The Backend and Qdrant are called by the other Applications without a Cloudera AI
   login (the Frontend keeps the login). The deploy Job protects them with a generated secret instead (see "Known limits").
2. **Check the quota.** By default the three Applications request **10 vCPU and 20 GB** in total: Qdrant 4 vCPU / 8 GB, Backend
   4 vCPU / 8 GB, Frontend 2 vCPU / 4 GB ([change them](docs/POC-GUIDE.md#sizing-the-applications)).
3. **Have your values ready:** a Gemini, OpenAI or Anthropic API key, and the Trino or Impala host, user and password.

## Step by step

**1. Import** (about 4 min until the first job starts)
- **AMPs** (left menu) -> **Deploy External** (top right).
- Project name, visibility **Private**, **Provide the Git URL** with **HTTPS**:
  `https://github.com/ano-cloudera/cloudera-ai-studio.git` (leave the branch empty).
- **Configure Project**. The form has no variables to fill in. Keep the runtime as shown (JupyterLab, Python 3.10, Standard), turn
  **Enable Spark** off (the app does not use it), and keep **Execute AMP setup steps** checked, then **Launch**.

> [!NOTE]
> The import has no variables to fill in. Just click **Launch**: a Cloudera AI form bug can save an edited value as `[object Object]`,
> which is why keys and credentials are added in **Project Settings -> Advanced** after the import (step 3).

**2. Wait for `install-tools`** (about 21 min)
- Follow it in **AMP Status**, or in the job log (markers `[1/7]` to `[7/7]`). The embedding model alone is about 2.3 GB.

**3. Add your variables** (a few minutes)
- **Project Settings -> Advanced**, button **+**: name and value, then **Submit**. Which variables: see the tables below.

**4. Deploy**
- **Jobs -> Deploy applications -> Run.** It builds the UI and creates the three Applications.
- The AMP already runs it once at the end of the import. Without keys that run only warns that no LLM key is set, so run it again now.
- Time: about 3 min (it builds the UI and starts the three Applications).

**5. Verify** (1 min)
- **Applications**: Qdrant, Backend and Frontend are **Running**.
- Open **Anywhere Frontend**: the badge at the top right reads **Platform Ready**.

**6. Configure the demo** (per PoC)
- In the Frontend: [Configure the demo](docs/DEMO-GUIDE.md) (LLM, Data Source, semantic layer, knowledge, MCP).

Expect about **30 minutes in total** from Launch to the first screen (measured twice on one workspace; yours will differ).

**Variables to add in Project Settings** (button **+**: name and value, then **Submit**). Add only the ones you fill in: the page refuses
to save a variable with an empty value.

**Required for a first demo** (one LLM key plus Trino):

| Variable | Example value |
|---|---|
| `GEMINI_API_KEY` | `AIzaSy...` |
| `TRINO_HOST` | `my-trino.dw-env.a1b2-c3d4.cloudera.site` |
| `TRINO_USER` | `workload-user` |
| `TRINO_PASSWORD` | `your-password` |

- Use `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` instead of Gemini if you prefer.
- `TRINO_HOST` is the host only: no `https://`, no trailing `/`.
- Data in Impala instead of Trino: use `IMPALA_HOST`, `IMPALA_USER`, `IMPALA_PASSWORD`.

**Optional**

| Variable | Add it when | Example value |
|---|---|---|
| `POSTGRES_PASSWORD` | A Data Source is PostgreSQL | `your-password` |
| `AMP_FORWARD_ENV` | A Data Source or MCP server needs other secrets | `MY_DB_PASSWORD,MY_TOOL_TOKEN` |
| `AMP_RUNTIME_ID` | The deploy log says `Runtime: not detected` | the runtime image name on your Jobs |
| `ENABLE_VLLM` | You serve your own model ([PoC guide](docs/POC-GUIDE.md#optional-vllm-your-own-model-on-a-gpu)) | `true` |
| `ENABLE_RERANKER` | Knowledge search over many or similar documents ([PoC guide](docs/POC-GUIDE.md#better-knowledge-search-optional-reranker)); adds a download of about 2 GB and raises the Backend to 16 GB | `true` |
| `TRINO_CATALOG`, `TRINO_SCHEMA` | Your tables are not in `hive` / `default` | `hive`, `default` |
| `ASK_DATA_UNDERSTANDING` | You want the language model to read each data question against the published model (metric, breakdown, filters, period), checked by code. Add it to `AMP_FORWARD_ENV` too | `llm` (default `rules`) |
| `ANSWER_CACHE` | `first` serves a recent answer to a repeated question at once (warm the demo questions by asking them once); `fallback` (default) answers live and serves the last answer only when the data source is down; `off` keeps nothing. Add it to `AMP_FORWARD_ENV` too | `first` |
| `AMP_SUBDOMAIN_PREFIX` | Another `anywhere-*` Application already exists in the workspace (set before the first deploy) | `anywhere2` |

For `AMP_FORWARD_ENV`, also add each listed name as its own variable; the Data Source then refers to it as `env://NAME`.

After adding variables, run the **Deploy applications** Job again.

**Day-2 operations**

| When | Do this |
|---|---|
| You added or changed a variable | Run the **Deploy applications** Job again (it copies the variables to the Applications and restarts them) |
| You pushed new code to GitHub | Run the **Update from GitHub** Job. It pulls, installs new Backend requirements if they changed, and redeploys (no Session needed). It stops without redeploying when nothing is new; it never merges or discards local edits and tells you what to do if it cannot pull |
| A variable shows `[object Object]` | In a Session: `python scripts/amp/set_env.py` (or `python scripts/amp/set_env.py NAME` for one variable); secrets are not echoed |
| You want to test the API access first | In a Session: `python scripts/amp/deploy.py --check` (read-only) |

Starting a new PoC? Follow the [PoC guide](docs/POC-GUIDE.md).

## If something goes wrong

| What you see | What to do |
|---|---|
| Deploy log: `runtime image must be specified in a project using runtimes` | The Job reads the runtime from the project's jobs. If it logs `Runtime: not detected`, add `AMP_RUNTIME_ID` with the runtime image name shown on your Jobs, then run the Job again |
| Deploy log: `project environment is not a valid environment JSON` or `variables that are not plain text` | A value was saved as `[object Object]` (a Cloudera AI form bug). In a Session run `python scripts/amp/set_env.py`, then run the Job again |
| Frontend shows **Platform Unavailable** | The Backend and Qdrant still require a Cloudera AI login. Ask the admin to enable unauthenticated Applications (see "Before you start"), then run the Job again |

## Known limits

- The Application subdomains are fixed (`anywhere-qdrant`, `anywhere-backend`, `anywhere-frontend`). If they collide in your workspace,
  add the project variable `AMP_SUBDOMAIN_PREFIX` before the first deploy.
- **Backend and Qdrant have no Cloudera AI login.** The deploy Job generates a secret (kept in `/home/cdsw/anywhere-studio-data/secrets/`,
  readable by project collaborators only). The Backend answers only under `<backend-url>/<secret>/...` (everything else is 404 except
  `/health`), and Qdrant requires an API key; the Frontend adds both for you, and the browser never sees them. Open the Backend API
  docs at `<backend-url>/<secret>/docs`. To use the Qdrant dashboard, set the project variable `QDRANT_API_KEY` to a value you choose
  and run the deploy Job again, then enter it in the dashboard. This is enough for demos and PoCs; it is not a replacement for real
  authentication, so do not load sensitive data.
- The deploy Job calls the Cloudera AI REST API with the key Cloudera AI provides to Jobs (`CDSW_APIV2_KEY`). It has been run end to end
  in one workspace only; report failures with the Job log.

## Documentation

| I want to | Read |
|---|---|
| Configure and run the demo (LLM, Data Source, semantic layer, knowledge, MCP, example questions) | [docs/DEMO-GUIDE.md](docs/DEMO-GUIDE.md) |
| Bring this to a new PoC, size the Applications, serve my own model with vLLM | [docs/POC-GUIDE.md](docs/POC-GUIDE.md) |
| Understand or repeat the installation by hand | [docs/MANUAL-INSTALL.md](docs/MANUAL-INSTALL.md) |
| Run it on my laptop | [docs/LOCAL-DEVELOPMENT.md](docs/LOCAL-DEVELOPMENT.md) |
| Try a second use case (fulfillment and delivery) and run its test plan | [samples/fulfillment](samples/fulfillment/README.md), [docs/TEST-PLAN.md](docs/TEST-PLAN.md) |

## Security notes

- No secrets are stored in the repository. Credentials are referenced as `env://VAR_NAME` and read from the environment.
- `.env`, local state (`runtime/`, `backend/var/`) and test output are git-ignored.
- All demo data and documents are synthetic.

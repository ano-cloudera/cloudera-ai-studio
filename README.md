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
- **Configure Project**, then **Launch**.

> [!WARNING]
> **Do not edit the variables form. Just click Launch.**
> A Cloudera AI form bug can save a typed value as `[object Object]`, and the deploy Job then fails. Add your keys and credentials in
> **Project Settings -> Advanced** after the import (step 3).

**2. Wait for `install-tools`** (about 21 min)
- Follow it in **AMP Status**, or in the job log (markers `[1/7]` to `[7/7]`). The embedding model alone is about 2.3 GB.

**3. Add your variables** (a few minutes)
- **Project Settings -> Advanced**, button **+**: name and value, then **Submit**. Which variables: see the tables below.

**4. Deploy**
- **Jobs -> Deploy applications -> Run.** It builds the UI and creates the three Applications.
- The AMP already runs it once at the end of the import. Without keys that run only warns that no LLM key is set, so run it again now.
- Time: not measured yet.

**5. Verify** (1 min)
- **Applications**: Qdrant, Backend and Frontend are **Running**.
- Open **Anywhere Frontend**: the badge at the top right reads **Platform Ready**.

**6. Configure the demo** (per PoC)
- In the Frontend: [Configure the demo](docs/DEMO-GUIDE.md) (LLM, Data Source, semantic layer, knowledge, MCP).

Expect about **30 minutes plus the deploy Job** before the first screen (measured once; yours will differ).

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

For `AMP_FORWARD_ENV`, also add each listed name as its own variable; the Data Source then refers to it as `env://NAME`.

After adding variables, run the **Deploy applications** Job again.

**Day-2 operations**

| When | Do this |
|---|---|
| You added or changed a variable | Run the **Deploy applications** Job again (it copies the variables to the Applications and restarts them) |
| You pulled new code | In a Session: `cd /home/cdsw && git pull`, then run the **Deploy applications** Job again |
| A variable shows `[object Object]` | In a Session: `python scripts/amp/set_env.py` (or `python scripts/amp/set_env.py NAME` for one variable); secrets are not echoed |
| You want to test the API access first | In a Session: `python scripts/amp/deploy.py --check` (read-only) |

Starting a new PoC? Follow the [PoC guide](docs/POC-GUIDE.md).

## If something goes wrong

| What you see | What to do |
|---|---|
| Deploy log: `runtime image must be specified in a project using runtimes` | The Job reads the runtime from the project's jobs. If it logs `Runtime: not detected`, add `AMP_RUNTIME_ID` with the runtime image name shown on your Jobs, then run the Job again |
| Deploy log: `project environment is not a valid environment JSON` or `variables that are not plain text` | The import form saved a value as `[object Object]`. In a Session run `python scripts/amp/set_env.py`, then run the Job again |
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

## Security notes

- No secrets are stored in the repository. Credentials are referenced as `env://VAR_NAME` and read from the environment.
- `.env`, local state (`runtime/`, `backend/var/`) and test output are git-ignored.
- All demo data and documents are synthetic.

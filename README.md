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
   to be configured with unauthenticated access**. The Backend and Qdrant are called by the other Applications without a login (the
   Frontend keeps the login), so use this for demos and PoCs, not for sensitive data.
2. **Check the quota.** By default the three Applications request **10 vCPU and 20 GB** in total: Qdrant 4 vCPU / 8 GB, Backend
   4 vCPU / 8 GB, Frontend 2 vCPU / 4 GB ([change them](docs/POC-GUIDE.md#sizing-the-applications)).
3. **Have your values ready:** a Gemini, OpenAI or Anthropic API key, and the Trino or Impala host, user and password.

## Step by step

| # | Step | What you do | Time (measured once, AWS workspace) |
|---|---|---|---|
| 1 | **Import** | **AMPs** (left menu) -> **Deploy External** (top right) -> the *Configure & Deploy AMP* form: project name, visibility **Private**, *Provide the Git URL* with **HTTPS**, Git URL `https://github.com/ano-cloudera/cloudera-ai-studio.git`, leave the branch empty -> **Configure Project**. **Do not edit the variables form**, click **Launch** (see the warning below). | about 4 min until the first job starts |
| 2 | **Wait for `install-tools`** | Watch **AMP Status** (or the job log, markers `[1/7]` to `[7/7]`). The embedding model is about 2.3 GB. | about 21 min |
| 3 | **Add your variables** | **Project Settings -> Advanced**, button **+**: name and value for each variable in the table below, then **Submit**. | a few minutes |
| 4 | **Deploy** | **Jobs -> Deploy applications -> Run**. It builds the UI and creates the three Applications. The AMP also runs it once at the end of the import; without keys that run only warns that no LLM key is set. | build and start: not timed yet |
| 5 | **Verify** | **Applications**: three Applications **Running**. Backend `/health/ready` must show `"core_ready": true`. Open **Anywhere Frontend**: the badge must read **Platform Ready**. | 1 min |
| 6 | **Configure the demo** | In the Frontend: [Configure the demo](docs/DEMO-GUIDE.md) (LLM, Data Source, semantic layer, knowledge, MCP). | per PoC |

Expect about **30 minutes plus the deploy Job** before the first screen (measured once; yours will differ).

> [!WARNING]
> **Do not edit the variables form at import. Just click Launch.**
> A Cloudera AI form bug can save a typed value as `[object Object]`, and the deploy Job then fails. Add your keys and credentials in
> **Project Settings -> Advanced** after the import (next table).

**Variables to add in Project Settings** (add only what you fill in: the page refuses to save a variable with an empty value):

| Variable | When |
|---|---|
| `GEMINI_API_KEY`, `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` | At least one LLM key |
| `TRINO_HOST`, `TRINO_USER`, `TRINO_PASSWORD` | Data in Trino (host only, without `https://`) |
| `IMPALA_HOST`, `IMPALA_USER`, `IMPALA_PASSWORD` | Data in Impala |
| `POSTGRES_PASSWORD` | Data Source is PostgreSQL |
| `AMP_FORWARD_ENV` | Names (comma separated) of other secrets a Data Source or MCP server needs, which you also add as variables; the Data Source refers to them as `env://NAME` |
| `AMP_RUNTIME_ID` | Only to force a runtime image; by default the runtime of the project's jobs is used |
| `ENABLE_VLLM=true`, `VLLM_MODEL_ID`, `AMP_VLLM_RUNTIME_ID`, `GPU_PROFILE` | Serving your own model, see the [PoC guide](docs/POC-GUIDE.md#optional-vllm-your-own-model-on-a-gpu) |

**Day-2 operations**

| When | Do this |
|---|---|
| You added or changed a variable | Run the **Deploy applications** Job again (it copies the variables to the Applications and restarts them) |
| You pulled new code | In a Session: `cd /home/cdsw && git pull`, then run the **Deploy applications** Job again |
| A variable shows `[object Object]` | In a Session: `python scripts/amp/set_env.py` (or `python scripts/amp/set_env.py NAME` for one variable); secrets are not echoed |
| You want to test the API access first | In a Session: `python scripts/amp/deploy.py --check` (read-only) |

Starting a new PoC? Follow the [PoC guide](docs/POC-GUIDE.md).

## If something goes wrong

| What you see | Cause | What to do |
|---|---|---|
| `install-tools` is marked failed although the log ends with `Setup complete.` | Older versions of the script ended with `SystemExit`, which the Cloudera AI job runner reports as failure | `git pull`, then **Resume** the AMP (or run the Job again; finished steps are skipped) |
| Deploy log: `runtime image must be specified in a project using runtimes` | The workspace needs a runtime image for each Application | The Job reads it from the project's jobs. If it logs `Runtime: not detected`, add `AMP_RUNTIME_ID` with the runtime image name |
| Deploy log: `project environment is not a valid environment JSON` or `variables that are not plain text` | The import form saved an edited value as `[object Object]` | Run `python scripts/amp/set_env.py` in a Session, then run the Job again |
| Project Settings: "The key and value are required" and Submit does nothing | A variable with an empty value is in the list | Delete that row with `-` (it was optional) or fill it in |
| Frontend shows **Platform Unavailable**, Backend `/health/ready` shows Qdrant `UnexpectedResponse` | The Backend and Qdrant still require a Cloudera AI login (HTTP 302 for server to server calls) | Ask the admin to enable unauthenticated Applications (see "Before you start"), then run the deploy Job again |
| Deploy log mentions creating an Application without a login | The admin setting is off | Same as above |
| `Warning: no LLM key is set` | No `GEMINI_API_KEY`, `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` yet | Add one in Project Settings and run the deploy Job again |

## Known limits

- The Application subdomains are fixed (`anywhere-qdrant`, `anywhere-backend`, `anywhere-frontend`). If they collide in your workspace,
  add the project variable `AMP_SUBDOMAIN_PREFIX` before the first deploy.
- The Backend and Qdrant run without a login (see "Before you start"). Do not load sensitive data into a demo workspace that others can reach.
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

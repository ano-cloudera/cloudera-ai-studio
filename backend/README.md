# Cloudera AI Studio — Backend (`backend`)

FastAPI + controlled LangGraph Ask Data backend for the accelerator. V2 does not call Agent Studio. It resolves Apache Ossie metrics first, permits a controlled single-view SQL fallback, validates every query with SQLGlot, executes read-only Impala, and asks the selected provider for a grounded result analysis/chart contract.

## Local run and tests

```bash
cd backend
python -m venv .venv
.venv/bin/pip install -r requirements.txt -r requirements-impala.txt
cp .env.example .env
PYTHONPATH=. .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
PYTHONPATH=. .venv/bin/pytest -q tests
```

`GET /health` is deliberately lightweight. `GET /health/ready` reports safe LLM, semantic, and Impala configuration readiness. `GET /models` reports configured availability. `GET /random-queries` supports `domain`, `difficulty`, and `limit`. `POST /chat` and `POST /chat/stream` accept `session_id`, `question`, `provider`, and the exact configured `model` returned by `/models`.

### Governed stack with tempo_agent_v3 (judge loop)

From repo root, one command starts agent v3 (`:9766`), backend v2 (`:8000`, routes Ask Data via `ASK_DATA_ROUTING=auto|ossie|v3`), and frontend (`:3000`):

```bash
./scripts/run-local-stack-governed.sh
```

Requires repo-root `.env` (Impala AWS profile + `GEMINI_API_KEY` for v3). Smoke without Impala: `TEMPO_MOCK_MODE=1 ./scripts/run-local-stack-governed.sh`.

Default engine is **`langgraph`** (KPI graph + judge + Impala). Set `TEMPO_AGENT_V3_ENGINE=deep` only for coordinator demos.

### Conversation memory (CAI)

Chat history is stored in **`backend/runtime/conversation_history.sqlite`** inside the application (no separate LightMemory service). For CAI, keep this path on persistent app storage; optional Postgres can replace SQLite later via the same `ConversationStore` interface.

Each turn stores the question, answer JSON, **query rows**, `status`/`strategy`, and a compact **`session_frame`** (`last_metric`, `last_dimensions`, `ranked_entities` for chart/table follow-ups). Analytic follow-ups use `session_context.py` (referential rewrite from `session_frame` + rows). Clarification-chip merging runs only when the prior turn was `CLARIFICATION` / `strategy=clarification` (or a legacy no-row choice prompt)—not via a word-count gate.

### Domain business graph (Phase C6)

Metadata graph in `knowledge/tempo_domain_graph.yaml` (no Agent Studio, no PuppyGraph required). It powers cabang/sales-office disambiguation, journey hints (Stock→Sell-In→B2B→SAT→OOS), and `inquiry_brief.business_context`. Toggle with `BUSINESS_GRAPH_ENABLED`. Numbers still come only from OSSIE + Impala.

### B3 management regression

Dry-run resolver/routing:

```bash
cd backend && PYTHONPATH=. python scripts/simulate_management_questions.py
```

Live (backend must be up, OSSIE-only recommended):

```bash
bash scripts/run-b3-live.sh
```

Management-style **multi-turn** UAT (same `session_id` per scenario, follow-up drills + clarification):

```bash
# OSSIE-only stack: ./scripts/run-local-stack-ossie-only.sh  (or governed stack)
cd backend && PYTHONPATH=. python scripts/run_uat_management_followup.py http://127.0.0.1:8000 gemini
```

Each turn is scored by **Gemini judge** (grounding, domain sell-in/sell-out, follow-up coherence) using rubrics in the YAML. Use `--skip-judge` for mechanical-only runs. Reports include `judge` per turn under `eval/uat_management_run_*.json`.

**5 questions × domain** (sales, b2b, stock_tempo, stock_sat, sat_oos, service_level, picking, unloading, promo, cross_domain):

```bash
cd backend && PYTHONPATH=. python scripts/run_uat_domain_5x5.py http://127.0.0.1:8000 gemini
# optional: --domain=b2b --skip-judge
```

Matrix: `eval/uat_domain_5x5.yaml`; reports: `eval/uat_domain_5x5_run_*.json`.

**5×5 follow-up UAT** (2 turns per scenario, shared `session_id`, referential drills):

```bash
cd backend && PYTHONPATH=. python scripts/run_uat_domain_5x5_followup.py http://127.0.0.1:8000 gemini
# one domain: --domain=b2b ; mechanical only: --skip-judge
bash scripts/run_uat_domain_5x5_followup_all_domains.sh http://127.0.0.1:8000 gemini
PYTHONPATH=. python scripts/merge_uat_domain_5x5_followup_reports.py eval/uat_domain_5x5_followup_run_*.json
```

Matrix: `eval/uat_domain_5x5_followup.yaml`. Latest merged judge summary: `eval/uat_domain_5x5_followup_merged_latest.json` (per-domain `uat_domain_5x5_followup_run_*.json` are gitignored).

## Configuration

Copy `.env.example` and set the selected provider plus Impala values. Model IDs are never hardcoded in the frontend. Qwen needs `QWEN_BASE_URL`, `QWEN_API_TOKEN`, and `QWEN_MODEL`; the legacy name `QWEN_API_KEY` remains an accepted alias. Gemini/OpenAI need an API key and model. Unconfigured providers remain unavailable without preventing startup. For the current Private Cloud deployment use the proven Impala GSSAPI + TLS values, query timeout, and a valid Kerberos ticket/service account. Never commit credentials.

Prompts live in `prompts/` and are resolved relative to the backend package, so CAI's working directory does not affect them. The copied `projects/reference_impala/ossie` files are the deployed 20-dataset/62-metric semantic authority.

## Cloudera AI Application

Create a dedicated CAI Application with the same Python 3.10 runtime pattern as V1. Entrypoint:

```text
backend/app_cai_backend.py
```

Set provider and Impala variables from `.env.example`. The launcher creates `backend/.venv-cai`, installs both requirement files, uses `CDSW_APP_PORT` (fallback `PORT`), and binds `127.0.0.1` because the CAI reverse proxy provides external HTTPS. Basic health URL is `/health`. Check CAI Application Logs for safe request IDs; credentials and raw exceptions are not returned to the browser.

## Troubleshooting

- Model disabled: inspect `/models`; set its model ID and required credential/base URL, then restart.
- Qwen returns a structurally different JSON object: the OpenAI-compatible adapter sends the exact Pydantic JSON Schema and performs one schema-correction retry before returning `INVALID_STRUCTURED_OUTPUT`.
- Pip reports an Impyla/Thrift resolution conflict: sync the latest `requirements-impala.txt`; Impyla 0.22.0 requires the pinned `thrift==0.16.0`.
- `IMPALA_AUTH_FAILED`: the coordinator returned 401/403 or another authentication failure. For the current Private Cloud environment use `GSSAPI`, port `21050`, TLS enabled, binary transport (`IMPALA_USE_HTTP_TRANSPORT=false`), and service name `impala`; verify a valid Kerberos ticket/keytab is available to the CAI process. Do not reuse the legacy LDAP/HTTP profile.
- `IMPALA_QUERY_FAILED`: authentication succeeded far enough to avoid an auth classification, but the connection/query still failed. Verify TLS, host/port, query permissions, and the published Gold view.
- SSE appears frozen: confirm the CAI proxy preserves `text/event-stream`; V2 sends `X-Accel-Buffering: no`, no-transform caching, and 15-second heartbeat comments. The frontend also aborts after 90 seconds and exposes a **Stop** button while a request is active.
- Optional provider has no outbound network: leave it configured as unavailable or select Qwen; startup remains healthy.

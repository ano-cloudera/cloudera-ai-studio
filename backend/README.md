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

### Conversation memory (CAI)

Chat history is stored in **`backend/runtime/conversation_history.sqlite`** inside the application (no separate LightMemory service). For CAI, keep this path on persistent app storage; optional Postgres can replace SQLite later via the same `ConversationStore` interface.

Each turn stores the question, answer JSON, **query rows**, `status`/`strategy`, and a compact **`session_frame`**: the question as it was read (`standalone_question`), its `metric`, `dimensions` and `scope`. Follow-ups work the way Cortex Analyst does it (`app/ask_data/conversation.py`): the language model rewrites each follow-up into a question that stands on its own, using the last three turns and their first rows, and the pipeline answers that question as if it were the first. A question that does not lean on the conversation is answered exactly as written. When the keyword matcher cannot tell which metric a question means, the model picks one from the published catalog (`choose_metric`); it may only pick a listed metric.

### Answers that explain (Genie style)

- **Depth follows the question.** The same reading of the turn also says whether a question needs several checks (`kind: "analysis"`: why, what to do or where to start, an overview or summary, how two things relate). Those go to agent mode (`app/ask_data/agent_mode.py`): a plan of 2 to 4 governed steps, each run through the normal pipeline, then one report with the finding, what it means, next actions and follow-up questions. A follow-up such as "kenapa bisa setinggi itu?" is planned from the question written out in full, and the metric of the step whose table is shown is kept for the next follow-up. A keyword pattern catches the common phrasings without the model. Set `AGENT_MODE_ENABLED=false` to turn it off.
- **Context next to the number** (`app/ask_data/answer_context.py`). A breakdown is answered next to the overall value of the same metric over the same filters and period (`data.overall_value`), so the analyst can say "about twice the overall 11.26%". The date range the data holds (`data.data_coverage`) is looked up once per source (cached 10 minutes); a period outside it is said so instead of shown as an empty result or a zero. Both are governed queries built by the backend and run with `context_query: true` in the state.

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

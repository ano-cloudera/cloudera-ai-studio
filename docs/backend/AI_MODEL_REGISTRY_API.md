# AI Model Registry API (M7A)

Base path: `/api/v1/ai` (requires `STATE_STORE=postgres` and `DATABASE_URL`).

## Providers

| Method | Path | Description |
|--------|------|-------------|
| GET | `/providers` | List providers (optional `provider_type`, `enabled`) |
| POST | `/providers` | Create provider |
| GET | `/providers/{id}` | Get provider |
| PATCH | `/providers/{id}` | Update provider |
| DELETE | `/providers/{id}` | Delete (409 `PROVIDER_IN_USE` if models exist) |
| POST | `/providers/{id}/test` | Test connection |

Create body (example):

```json
{
  "name": "Cloudera AI Inference",
  "key": "cai_inference",
  "provider_type": "OPENAI_COMPATIBLE",
  "base_url": "https://inference.example/v1",
  "secret_ref": "env://QWEN_API_KEY",
  "config_json": { "test_strategy": "AUTO" }
}
```

Provider responses expose `secret_configured` and masked `secret_ref` (`env://VAR` only). Resolved secrets are never returned.

## Models

| Method | Path | Description |
|--------|------|-------------|
| GET | `/models` | List (`provider_id`, `model_type`, `enabled`) |
| POST | `/models` | Create model |
| GET | `/models/{id}` | Get model |
| PATCH | `/models/{id}` | Update model |
| DELETE | `/models/{id}` | Delete (409 `MODEL_IN_USE` if assigned) |
| POST | `/models/{id}/test` | Validate model |

## Assignments

| Method | Path | Description |
|--------|------|-------------|
| GET | `/assignments` | All capabilities with effective resolution |
| PUT | `/assignments/{capability}` | Set assignment |
| DELETE | `/assignments/{capability}` | Remove project-scoped assignment |

Capabilities: `CHAT_DEFAULT`, `ASK_DATA`, `RAG_GENERATION`, `SKILLS`, `EMBEDDING`, `RERANKER`.

Assignment validation:

- Chat capabilities require `CHAT` models
- `EMBEDDING` requires `EMBEDDING`
- `RERANKER` requires `RERANKER`

## Test responses

```json
{
  "status": "READY",
  "latency_ms": 210,
  "provider_type": "OPENAI_COMPATIBLE",
  "error_code": null,
  "message": null
}
```

Failure uses normalized `error_code` (e.g. `AUTHENTICATION_FAILED`, `TEST_TIMEOUT`).

## Error codes

`PROVIDER_NOT_FOUND`, `MODEL_NOT_FOUND`, `PROVIDER_DISABLED`, `MODEL_DISABLED`, `AUTHENTICATION_FAILED`, `PROVIDER_UNREACHABLE`, `MODEL_INVALID`, `MODEL_IN_USE`, `PROVIDER_IN_USE`, `INVALID_ASSIGNMENT`, `SECRET_NOT_FOUND`, `TEST_TIMEOUT`

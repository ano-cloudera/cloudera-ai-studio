# Connector Registry Design (C1)

## Purpose

The connector registry stores **reusable datasource connections** per workspace/project. It is separate from the accelerator **internal** PostgreSQL (`DATABASE_URL` / platform state).

## Model

Table `connectors`:

- Scoped by `workspace_id` + `project_id` + stable `key`
- Typed `config` JSON (validated per `connector_type`)
- `secret_ref` only (e.g. `env://DEMO_POSTGRES_PASSWORD`) — no plaintext passwords in DB or API

Statuses: `ACTIVE`, `INACTIVE`, `ERROR`. Last test fields: `last_tested_at`, `last_test_status`, `last_test_message`.

## Secret providers

`EnvironmentSecretProvider` resolves `env://VAR_NAME`. Future: external secret managers.

API returns `credentials_configured` and masked `secret_ref`, never secret values.

## Adapters

`ConnectorFactory` → `ImpalaConnector` | `TrinoConnector` | `PostgresConnector`.

`DatasourceConnector` contract:

- `test_connection()`
- `get_capabilities()`
- `list_catalogs()` / `list_schemas()` / `list_tables()` / `describe_table()` (as supported)
- `execute_readonly_query()` with row limits

SQL safety: SQLGlot-based read-only guard (`SELECT` / `WITH`; rejects DML/DDL).

## Ask Data

**Unchanged in C1.** Legacy Impala/DuckDB backend configuration remains the Ask Data runtime. Connector registry is foundation for C2+.

## Local dev example (external Postgres)

| Field | Example |
|-------|---------|
| type | `postgres` |
| host | `127.0.0.1` |
| database | `demo_data` |
| secret_ref | `env://DEMO_POSTGRES_PASSWORD` |

Internal state DB may be `postgresql://…/accelerator_state` — a different database.

Seed: `python scripts/seed_connectors.py` (idempotent, secret refs only).

## C2 — Metadata discovery

`MetadataDiscoveryService` provides normalized browse APIs:

- Catalogs / schemas / tables (pagination, `search`, `table_type`, `refresh=true`)
- `POST .../metadata/describe` → `TableDetail` with `normalized_type` on columns
- `POST .../metadata/preview` → bounded read-only sample (max 100 rows, no arbitrary SQL)
- Optional `GET .../metadata/summary` (bounded counts)

Identifier validation blocks injection; PostgreSQL uses parameterized queries. Short TTL in-memory cache (`CONNECTOR_METADATA_CACHE_TTL_SECONDS`, default 60) for list endpoints — not used for previews.

Connection test returns phases, `default_catalog` / `default_schema`, and normalized `error_code` when failed.

## Semantic Layer integration (C4)

- Delete blocked when semantic entities reference connector (`GET .../references`)
- Table → entity import APIs under `/api/v1/semantic/versions/{id}/entities/import*`
- Credentials never copied into semantic metadata or OSSIE artifacts

See [CONNECTOR_SEMANTIC_INTEGRATION.md](../architecture/CONNECTOR_SEMANTIC_INTEGRATION.md).

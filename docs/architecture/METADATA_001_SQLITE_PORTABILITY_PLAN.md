# METADATA-001 SQLite portability plan

Input: [CAI_3_APP_PERSISTENCE_ARCHITECTURE_AUDIT.md](./CAI_3_APP_PERSISTENCE_ARCHITECTURE_AUDIT.md)

## Incompatibility inventory (resolved)

| ID | File / symbol | Prior behavior | SQLite replacement | Risk |
|----|---------------|----------------|--------------------|------|
| PG-T01 | `platform_models.py` `JSONB`, `UUID` | Postgres-only ORM types | `PlatformJSON`, `PlatformUUID` (`app/db/types.py`) | Low |
| PG-T02 | Alembic revisions | `postgresql.UUID/JSONB`, `'{}'::jsonb` | `ddl_types.UUID/JSON`, batch FK helpers | Medium |
| PG-T03 | Alembic FK after create | `op.create_foreign_key` | `ddl_types.create_foreign_key` (batch on SQLite) | Medium |
| PG-T04 | Alembic unique after create | `op.create_unique_constraint` | Inline `UniqueConstraint` in `create_table` | Low |
| PG-T05 | `deps.require_postgres_settings` | 503 unless postgres | `require_platform_settings` + `DATABASE_URL` dialect check | Low |
| PG-T06 | `readiness._postgres_check` | Postgres-only core gate | `_metadata_database_check` (Postgres + SQLite) | Low |
| PG-T07 | `document_service.py` JSON sort | `.astext` | `json_int_field()` | Low |
| PG-T08 | `factory._wants_postgres` | `STATE_STORE=postgres` | `_uses_platform_database()` (URL-based) | Low |

No `ON CONFLICT`, advisory locks, or Postgres-only raw SQL found in application services.

## Alembic strategy

**Choice: A — make existing migrations portable** (with SQLite batch helpers).

- Preserves revision history and PostgreSQL upgrade path.
- `env.py` enables `render_as_batch` for SQLite.
- Fresh SQLite installs run `alembic upgrade head` (proven in evidence).

## Demo data migration (Postgres → SQLite)

**Selected strategy:** **fresh bootstrap** for Golden Banking on CAI sim (`register_banking_*.py` seeds), not automatic PG dump.

Optional future: `scripts/migrate_metadata_postgres_to_sqlite.py` (dry-run, row counts) — not required for METADATA-001 local acceptance.

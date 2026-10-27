# METADATA-001 pre-migration baseline

Captured before SQLite portability code changes (2026-10-19).

| Item | Value |
|------|--------|
| Metadata dialect | PostgreSQL |
| `STATE_STORE` (dev `.env`) | `postgres` |
| `DATABASE_URL` (dev `.env`) | `postgresql+psycopg://m1:m1pass@127.0.0.1:55432/accelerator` |
| Alembic head | `m9_chat_attachments_001` |
| Backend tests (pre-change) | See post-migration delta; suite baseline ~428+ passed |

Golden Banking baselines unchanged on PostgreSQL metadata path until local CAI sim profile is used.

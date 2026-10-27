#!/usr/bin/env bash
# Apply Alembic migrations for accelerator platform PostgreSQL.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

if [ -f "$ROOT/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env"
  set +a
fi

if [ -z "${DATABASE_URL:-}" ]; then
  echo "DATABASE_URL is not set. Platform migrations apply only when using PostgreSQL (STATE_STORE=postgres)." >&2
  exit 1
fi

if [ -f "$ROOT/.venv/bin/activate" ]; then
  # shellcheck disable=SC1091
  source "$ROOT/.venv/bin/activate"
fi

export PYTHONPATH="$ROOT/backend:${PYTHONPATH:-}"
cd "$ROOT/backend"

echo "Current revision:"
alembic current || true
echo ""
echo "Upgrading to head…"
alembic upgrade head
echo ""
echo "Migration status:"
alembic current

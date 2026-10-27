#!/usr/bin/env bash
# Start backend with SQLite platform metadata under runtime/cai-sim (METADATA-001 local sim).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PRESET_CAI_DATA_DIR="${CAI_DATA_DIR:-}"
# shellcheck disable=SC1091
set -a
source "$ROOT/deployment/profiles/cai-sim-local.env"
if [[ -f "$ROOT/.env" ]]; then
  source "$ROOT/.env"
  source "$ROOT/deployment/profiles/cai-sim-local.env"
fi
set +a
if [[ -n "$PRESET_CAI_DATA_DIR" ]]; then
  export CAI_DATA_DIR="$PRESET_CAI_DATA_DIR"
fi

export UVICORN_WORKERS="${UVICORN_WORKERS:-1}"
SIM_ROOT="${CAI_DATA_DIR:-runtime/cai-sim}"
if [[ "$SIM_ROOT" != /* ]]; then
  SIM_ROOT="$ROOT/$SIM_ROOT"
fi
export CAI_DATA_DIR="$SIM_ROOT"
mkdir -p "$SIM_ROOT/metadata" "$SIM_ROOT/documents" "$SIM_ROOT/var/semantic-runtime"
DB_FILE="$SIM_ROOT/metadata/studio.db"
export CAI_DATA_DIR="$SIM_ROOT"
export CAI_SIM_METADATA=1
export CAI_SIM_DATABASE_URL="sqlite+pysqlite:///${DB_FILE}"
export CAI_SIM_DOCUMENT_STORAGE_ROOT="$SIM_ROOT/documents"
export CAI_SIM_SEMANTIC_RUNTIME_STORAGE_ROOT="$SIM_ROOT/var/semantic-runtime"
export DATABASE_URL="$CAI_SIM_DATABASE_URL"
export DOCUMENT_STORAGE_ROOT="$CAI_SIM_DOCUMENT_STORAGE_ROOT"
export SEMANTIC_RUNTIME_STORAGE_ROOT="$CAI_SIM_SEMANTIC_RUNTIME_STORAGE_ROOT"
export STATE_STORE=sqlite
export DEPLOYMENT_PROFILE=cai-sim-local

if [[ ! -f "$DB_FILE" ]]; then
  echo "Bootstrapping SQLite metadata at $DB_FILE"
  (cd "$ROOT/backend" && DATABASE_URL="$DATABASE_URL" PYTHONPATH=. "$ROOT/.venv/bin/alembic" upgrade head)
fi
echo "Ensuring platform seed (workspace/project) in SQLite metadata"
(cd "$ROOT/backend" && DATABASE_URL="$DATABASE_URL" PYTHONPATH=. "$ROOT/.venv/bin/python" - <<'PY'
from app.core.config import get_settings
from app.stores.factory import init_platform_metadata

get_settings.cache_clear()
init_platform_metadata(get_settings())
PY
)

exec "$ROOT/scripts/dev-backend.sh" "$@"

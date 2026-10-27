#!/usr/bin/env bash
# Production-safe Backend CAI Application launcher (single worker, 0.0.0.0).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PY="${ROOT}/.venv/bin/python"

usage() {
  cat <<EOF
Usage: $(basename "$0") <start|stop|status|migrate>

Environment (required for start):
  CAI_DATA_DIR          Persistent root (NFS mount)
  DATABASE_URL          Platform metadata DSN (sqlite or postgres)
  DOCUMENT_STORAGE_ROOT Relative to CAI_DATA_DIR or absolute
  SEMANTIC_RUNTIME_STORAGE_ROOT Relative to CAI_DATA_DIR or absolute
  QDRANT_URL            Qdrant service URL (Backend client)
  CORS_ORIGINS          Frontend origin(s)

Optional:
  BACKEND_HOST          Default 0.0.0.0
  BACKEND_PORT / PORT   Default 8001
  UVICORN_WORKERS       Must be 1 for SQLite metadata (enforced)
  CAI_ENV_FILE          Extra env file to source before start
  CAI_PLATFORM_SEED     Set to 1 to run idempotent platform seed on start
  CAI_SKIP_MIGRATE      Set to 1 to skip alembic upgrade
EOF
}

cmd="${1:-start}"
BACKEND_HOST="${BACKEND_HOST:-0.0.0.0}"
BACKEND_PORT="${BACKEND_PORT:-${PORT:-8001}}"
export UVICORN_WORKERS="${UVICORN_WORKERS:-1}"

_preset_cai_data_dir="${CAI_DATA_DIR:-}"
_preset_database_url="${DATABASE_URL:-}"
_preset_document_root="${DOCUMENT_STORAGE_ROOT:-}"
_preset_semantic_root="${SEMANTIC_RUNTIME_STORAGE_ROOT:-}"
_preset_qdrant_url="${QDRANT_URL:-}"
_preset_state_store="${STATE_STORE:-}"
_preset_cors="${CORS_ORIGINS:-}"

if [[ -f "${CAI_ENV_FILE:-}" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$CAI_ENV_FILE"
  set +a
elif [[ -f "$ROOT/deployment/profiles/cai.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/deployment/profiles/cai.env"
  set +a
fi

if [[ -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env"
  set +a
fi

[[ -n "$_preset_cai_data_dir" ]] && export CAI_DATA_DIR="$_preset_cai_data_dir"
[[ -n "$_preset_database_url" ]] && export DATABASE_URL="$_preset_database_url"
[[ -n "$_preset_document_root" ]] && export DOCUMENT_STORAGE_ROOT="$_preset_document_root"
[[ -n "$_preset_semantic_root" ]] && export SEMANTIC_RUNTIME_STORAGE_ROOT="$_preset_semantic_root"
[[ -n "$_preset_qdrant_url" ]] && export QDRANT_URL="$_preset_qdrant_url"
[[ -n "$_preset_state_store" ]] && export STATE_STORE="$_preset_state_store"
[[ -n "$_preset_cors" ]] && export CORS_ORIGINS="$_preset_cors"

export BACKEND_HOST BACKEND_PORT UVICORN_WORKERS
export BACKEND_PID_FILE="${BACKEND_PID_FILE:-$ROOT/.tmp/cai-backend-${BACKEND_PORT}.pid}"
export BACKEND_LOG_FILE="${BACKEND_LOG_FILE:-$ROOT/.tmp/cai-backend-${BACKEND_PORT}.log}"
export PYTHONPATH="${ROOT}/backend${PYTHONPATH:+:${PYTHONPATH}}"

_resolve_cai_paths() {
  [[ -n "${CAI_DATA_DIR:-}" ]] || return 0
  local sim="$CAI_DATA_DIR"
  if [[ "$sim" != /* ]]; then
    sim="$ROOT/$sim"
  fi
  export CAI_DATA_DIR="$sim"
  if [[ -z "${DATABASE_URL:-}" ]] && [[ "${STATE_STORE:-}" == "sqlite" ]]; then
    export DATABASE_URL="sqlite+pysqlite:///${sim}/metadata/studio.db"
  fi
  if [[ -n "${DOCUMENT_STORAGE_ROOT:-}" && "${DOCUMENT_STORAGE_ROOT}" != /* ]]; then
    export DOCUMENT_STORAGE_ROOT="${sim}/${DOCUMENT_STORAGE_ROOT}"
  elif [[ -z "${DOCUMENT_STORAGE_ROOT:-}" ]]; then
    export DOCUMENT_STORAGE_ROOT="${sim}/documents"
  fi
  if [[ -n "${SEMANTIC_RUNTIME_STORAGE_ROOT:-}" && "${SEMANTIC_RUNTIME_STORAGE_ROOT}" != /* ]]; then
    export SEMANTIC_RUNTIME_STORAGE_ROOT="${sim}/${SEMANTIC_RUNTIME_STORAGE_ROOT}"
  elif [[ -z "${SEMANTIC_RUNTIME_STORAGE_ROOT:-}" ]]; then
    export SEMANTIC_RUNTIME_STORAGE_ROOT="${sim}/var/semantic-runtime"
  fi
  export STATE_STORE="${STATE_STORE:-sqlite}"
  export DEPLOYMENT_PROFILE="${DEPLOYMENT_PROFILE:-cai}"
}

case "$cmd" in
  migrate)
    _resolve_cai_paths
    CAI_DATA_DIR="${CAI_DATA_DIR:-/data/cai}" "$ROOT/scripts/cai/init-storage.sh"
    [[ -n "${DATABASE_URL:-}" ]] || { echo "DATABASE_URL required for migrate" >&2; exit 1; }
    cd "$ROOT/backend"
    DATABASE_URL="$DATABASE_URL" "$PY" -m alembic upgrade head
    ;;
  start)
    _resolve_cai_paths
    if [[ "$UVICORN_WORKERS" != "1" ]]; then
      echo "ERROR: UVICORN_WORKERS must be 1 for CAI PoC (SQLite metadata safety)" >&2
      exit 1
    fi
    CAI_DATA_DIR="${CAI_DATA_DIR:?CAI_DATA_DIR required}" "$ROOT/scripts/cai/init-storage.sh"
    preflight_cmd=("$PY" "$ROOT/scripts/cai/preflight.py")
    [[ "${CAI_PREFLIGHT_STRICT:-1}" == "1" ]] && preflight_cmd+=(--strict)
    "${preflight_cmd[@]}" || exit 1
    if [[ "${CAI_SKIP_MIGRATE:-0}" != "1" ]] && [[ -n "${DATABASE_URL:-}" ]]; then
      cd "$ROOT/backend"
      DATABASE_URL="$DATABASE_URL" "$PY" -m alembic upgrade head
    fi
    if [[ "${CAI_PLATFORM_SEED:-0}" == "1" ]]; then
      cd "$ROOT/backend"
      DATABASE_URL="${DATABASE_URL:-}" PYTHONPATH=. "$PY" - <<'PY'
from app.core.config import get_settings
from app.stores.factory import init_platform_metadata

get_settings.cache_clear()
init_platform_metadata(get_settings())
PY
    fi
    # shellcheck disable=SC1091
    source "$ROOT/scripts/lib/backend-common.sh"
    export BACKEND_HOST BACKEND_PORT CAI_DEPLOYMENT_PRESERVE_ENV=1
    backend_start
    ;;
  stop)
    # shellcheck disable=SC1091
    source "$ROOT/scripts/lib/backend-common.sh"
    export BACKEND_HOST BACKEND_PORT
    backend_stop
    ;;
  status)
    # shellcheck disable=SC1091
    source "$ROOT/scripts/lib/backend-common.sh"
    export BACKEND_HOST BACKEND_PORT
    backend_status || true
    ;;
  -h | --help | help)
    usage
    ;;
  *)
    echo "Unknown command: $cmd" >&2
    usage >&2
    exit 1
    ;;
esac

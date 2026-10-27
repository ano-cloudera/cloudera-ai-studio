#!/usr/bin/env bash
# Idempotent local accelerator bootstrap (no destructive actions).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

PROFILE="${DEPLOYMENT_PROFILE:-local}"
echo "==> Cloudera AI Accelerator bootstrap (profile=${PROFILE})"

if [ ! -f "$ROOT/.env" ]; then
  if [ -f "$ROOT/config/examples/accelerator.env.example" ]; then
    cp "$ROOT/config/examples/accelerator.env.example" "$ROOT/.env"
    echo "Created .env from config/examples/accelerator.env.example — edit secrets before production use."
  else
    cp "$ROOT/.env.example" "$ROOT/.env"
    echo "Created .env from .env.example"
  fi
fi

set -a
# shellcheck disable=SC1091
source "$ROOT/.env"
set +a

if [ -f "$ROOT/deployment/profiles/local.env" ]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/deployment/profiles/local.env"
  set +a
fi

if [ -z "${PYTHON_BIN:-}" ]; then
  if [ -x /opt/homebrew/bin/python3.10 ]; then
    PYTHON_BIN=/opt/homebrew/bin/python3.10
  else
    PYTHON_BIN=python3.10
  fi
fi
command -v "$PYTHON_BIN" >/dev/null || { echo "Python 3.10+ required (set PYTHON_BIN)." >&2; exit 1; }

venv_needs_recreate=0
if [ ! -d "$ROOT/.venv" ]; then
  venv_needs_recreate=1
elif [ -f "$ROOT/.venv/pyvenv.cfg" ] && grep -q "enterprise-ai-poc" "$ROOT/.venv/pyvenv.cfg" 2>/dev/null; then
  echo "WARN: .venv pyvenv.cfg references source monorepo; recreating local venv." >&2
  venv_needs_recreate=1
elif [ -x "$ROOT/.venv/bin/python3.10" ]; then
  py_real="$(cd "$ROOT/.venv/bin" && readlink -f python3.10 2>/dev/null || true)"
  if [[ -n "$py_real" && "$py_real" == *"enterprise-ai-poc"* ]]; then
    echo "WARN: .venv python resolves into source monorepo; recreating local venv." >&2
    venv_needs_recreate=1
  fi
fi
if [ "$venv_needs_recreate" -eq 1 ]; then
  deactivate 2>/dev/null || true
  unset VIRTUAL_ENV
  rm -rf "$ROOT/.venv"
  env -i HOME="${HOME:-/tmp}" PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin" \
    "$PYTHON_BIN" -m venv "$ROOT/.venv"
fi
# shellcheck disable=SC1091
source "$ROOT/.venv/bin/activate"
python -m pip install -q --upgrade pip
pip install -q -r "$ROOT/backend/requirements.txt"

mkdir -p "$ROOT/backend/runtime/document_storage"
mkdir -p "$ROOT/backend/var/semantic-runtime"
mkdir -p "$ROOT/backend/runtime"

export PYTHONPATH="$ROOT/backend:${PYTHONPATH:-}"

if [ "${STATE_STORE:-sqlite}" = "postgres" ] && [ -n "${DATABASE_URL:-}" ]; then
  bash "$ROOT/scripts/migration/upgrade-db.sh"
  python "$ROOT/backend/scripts/platform_bootstrap.py"
else
  echo "Skipping Postgres migrations (STATE_STORE=${STATE_STORE:-sqlite})."
fi

if [ ! -d "$ROOT/frontend/node_modules" ]; then
  (cd "$ROOT/frontend" && npm install)
fi

python "$ROOT/scripts/doctor.py" || true

echo ""
echo "Bootstrap complete. Start stack:"
echo "  ./scripts/dev-stack.sh"
echo "  Web: http://127.0.0.1:3001   API: http://127.0.0.1:8001/docs"

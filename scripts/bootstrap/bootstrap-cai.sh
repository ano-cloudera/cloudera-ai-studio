#!/usr/bin/env bash
# CAI / pilot bootstrap — validates env, storage, migrations (non-destructive).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

echo "==> Cloudera AI Accelerator bootstrap (CAI profile)"

if [ ! -f "$ROOT/.env" ]; then
  echo "Missing .env — copy config/examples/accelerator.env.example and set CAI values." >&2
  exit 1
fi

set -a
# shellcheck disable=SC1091
source "$ROOT/.env"
set +a

if [ -f "$ROOT/deployment/profiles/cai.env" ]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/deployment/profiles/cai.env"
  set +a
fi

export DEPLOYMENT_PROFILE="${DEPLOYMENT_PROFILE:-cai}"
export PYTHONPATH="$ROOT/backend:${PYTHONPATH:-}"

for path in "${DOCUMENT_STORAGE_ROOT:-}" "${SEMANTIC_RUNTIME_STORAGE_ROOT:-}"; do
  if [ -n "$path" ]; then
    if [ ! -d "$path" ]; then
      echo "Storage path missing: $path (mount NFS before bootstrap)" >&2
      exit 1
    fi
    if [ ! -w "$path" ]; then
      echo "Storage path not writable: $path" >&2
      exit 1
    fi
  fi
done

if [ "${STATE_STORE:-postgres}" != "postgres" ]; then
  echo "WARNING: CAI pilot expects STATE_STORE=postgres for durable platform metadata." >&2
fi

bash "$ROOT/scripts/migration/upgrade-db.sh"
python "$ROOT/backend/scripts/platform_bootstrap.py"
python "$ROOT/scripts/doctor.py"

echo ""
echo "CAI bootstrap checks passed. Deploy backend + frontend applications with this .env."

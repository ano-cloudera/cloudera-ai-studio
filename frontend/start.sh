#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

# Load .env.local only when BACKEND_API_URL is not already set (e.g. run-local-stack-governed.sh).
if [[ -z "${BACKEND_API_URL:-}" && -f .env.local ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env.local
  set +a
fi

export BACKEND_API_URL="${BACKEND_API_URL:-${NEXT_PUBLIC_BACKEND_URL:-http://127.0.0.1:8000}}"

if [[ -n "${PORT:-}" ]]; then
  exec npm run dev -- --port "$PORT"
fi
# No fixed port — Next picks 3000 or the next free port (avoids EADDRINUSE crash).
exec npm run dev

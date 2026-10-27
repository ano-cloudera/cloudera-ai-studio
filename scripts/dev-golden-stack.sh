#!/usr/bin/env bash
# Golden local stack: CAI sim backend (:8001) + Next dev frontend (:3001).
# Run in a dedicated terminal and leave it open (frontend runs in foreground).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

set -a
# shellcheck disable=SC1091
source "$ROOT/deployment/profiles/cai-sim-local.env"
[[ -f "$ROOT/.env" ]] && source "$ROOT/.env"
set +a

export BANKING_DEMO_PG_PASSWORD="${BANKING_DEMO_PG_PASSWORD:-m1pass}"
export BACKEND_API_URL="${BACKEND_API_URL:-http://127.0.0.1:8001}"
export NEXT_PUBLIC_BACKEND_URL="${NEXT_PUBLIC_BACKEND_URL:-http://127.0.0.1:8001}"

echo "==> Starting backend (CAI sim SQLite) on :8001"
"$ROOT/scripts/dev-cai-sim-backend.sh" start

if ! curl -sf "http://127.0.0.1:8001/health/ready" >/dev/null; then
  echo "ERROR: Backend not ready. See .tmp/backend-8001.log" >&2
  exit 1
fi

echo "==> Starting frontend on :3001 (Ctrl+C stops frontend only)"
echo "    Open: http://127.0.0.1:3001"
cd "$ROOT/frontend"
if [[ ! -d node_modules ]]; then
  npm install
fi
exec npm run dev -- -p 3001

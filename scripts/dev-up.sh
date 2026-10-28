#!/usr/bin/env bash
# Start local Cloudera AI Studio stack (Docker deps + backend + frontend).
# Run from your own Terminal.app / iTerm tab — not from a short-lived automation shell.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

docker start m1-pg-smoke m2-qdrant 2>/dev/null || true

"$ROOT/scripts/dev-backend.sh" start
"$ROOT/scripts/dev-frontend.sh" restart-clean

echo ""
"$ROOT/scripts/dev-backend.sh" status
"$ROOT/scripts/dev-frontend.sh" status
echo ""
echo "Open: http://127.0.0.1:3001"
echo "Logs: tail -f .tmp/backend-8001.log .tmp/frontend-3001.log"
echo "Stop: ./scripts/dev-down.sh"

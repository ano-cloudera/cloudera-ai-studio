#!/usr/bin/env bash
# Start backend (:8001) + frontend dev (:3001) for Cloudera AI Studio.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
chmod +x "$ROOT/scripts/dev-backend.sh" 2>/dev/null || true
"$ROOT/scripts/dev-backend.sh" start
cd "$ROOT/frontend"
if [[ ! -d node_modules ]]; then
  npm install
fi
exec npm run dev -- -p 3001

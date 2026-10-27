#!/usr/bin/env bash
# Start Next.js dev server on :3001 (Cloudera AI Studio frontend).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/frontend"
if [[ ! -d node_modules ]]; then
  npm install
fi
exec npm run dev -- -p "${FRONTEND_DEV_PORT:-3001}"

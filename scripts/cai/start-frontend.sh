#!/usr/bin/env bash
# Production Frontend CAI Application launcher (next start, not dev).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
FE="$ROOT/frontend"
PORT="${PORT:-3000}"
HOST="${HOST:-0.0.0.0}"
PID_FILE="$FE/.next-prod.pid"
LOG="${ROOT}/.tmp/cai-frontend-${PORT}.log"

cmd="${1:-start}"

frontend_build_if_needed() {
  if [[ ! -d "$FE/.next" ]]; then
    echo "Building frontend (production)…"
    (cd "$FE" && npm run build)
  fi
}

case "$cmd" in
  start)
    frontend_build_if_needed
    mkdir -p "${ROOT}/.tmp"
    if curl -sf -o /dev/null "http://127.0.0.1:${PORT}/" 2>/dev/null; then
      echo "ALREADY_RUNNING port=$PORT"
      exit 0
    fi
    (
      cd "$FE"
      export BACKEND_API_URL="${BACKEND_API_URL:?BACKEND_API_URL required}"
      export NEXT_PUBLIC_BACKEND_URL="${NEXT_PUBLIC_BACKEND_URL:-$BACKEND_API_URL}"
      export PORT HOST
      exec npm run start
    ) >>"$LOG" 2>&1 &
    echo $! >"$PID_FILE"
    for _ in $(seq 1 90); do
      code=$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:${PORT}/" 2>/dev/null || echo 000)
      if [[ "$code" == "200" ]]; then
        echo "FRONTEND_STARTED port=$PORT log=$LOG"
        exit 0
      fi
      sleep 1
    done
    echo "Frontend failed to become ready; see $LOG" >&2
    exit 1
    ;;
  stop)
    if [[ -f "$PID_FILE" ]]; then
      kill "$(cat "$PID_FILE")" 2>/dev/null || true
      rm -f "$PID_FILE"
    fi
    lsof -ti ":$PORT" 2>/dev/null | xargs kill 2>/dev/null || true
    echo "Frontend stopped port=$PORT"
    ;;
  build)
    (cd "$FE" && npm run build)
    ;;
  *)
    echo "Usage: $0 {start|stop|build}" >&2
    exit 1
    ;;
esac

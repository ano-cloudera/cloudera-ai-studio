#!/usr/bin/env bash
# Canonical local frontend lifecycle (Next.js on :3001).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
# shellcheck source=../frontend/scripts/lib/frontend-dev-common.sh
source "$ROOT/frontend/scripts/lib/frontend-dev-common.sh"

LOG_FILE="${ROOT}/.tmp/frontend-3001.log"
PID_FILE="$FRONTEND_DIR/.next-dev.pid"

frontend_start() {
  mkdir -p "${ROOT}/.tmp"
  if frontend_dev_wait_http "http://127.0.0.1:$FRONTEND_DEV_PORT/" 1; then
    echo "ALREADY_RUNNING port=$FRONTEND_DEV_PORT"
    return 0
  fi
  if [[ ! -d "$FRONTEND_DIR/node_modules" ]]; then
    (cd "$FRONTEND_DIR" && npm install)
  fi
  echo "Starting Next.js on :$FRONTEND_DEV_PORT (log: $LOG_FILE)…"
  {
    echo "======== frontend start $(date -u +%Y-%m-%dT%H:%M:%SZ) ========"
  } >>"$LOG_FILE"
  # Run `next` directly — `nohup npm` often exits after spawning and the dev server dies with the shell.
  (
    cd "$FRONTEND_DIR"
    export BACKEND_API_URL="${BACKEND_API_URL:-http://127.0.0.1:8001}"
    export NEXT_PUBLIC_BACKEND_URL="${NEXT_PUBLIC_BACKEND_URL:-http://127.0.0.1:8001}"
    export NEXT_PUBLIC_APP_NAME="Cloudera AI Studio"
    export NEXT_PUBLIC_PRODUCT_NAME="Cloudera AI Studio"
    export NEXT_PUBLIC_PRODUCT_SHORT_NAME="AI Studio"
    export NEXT_PUBLIC_APP_SUBTITLE="AI Studio"
    nohup ./node_modules/.bin/next dev -H 0.0.0.0 -p "$FRONTEND_DEV_PORT" >>"$LOG_FILE" 2>&1 </dev/null &
    echo $! >"$PID_FILE"
  )
  disown 2>/dev/null || true
  if ! frontend_dev_wait_ready "http://127.0.0.1:$FRONTEND_DEV_PORT/"; then
    if [[ -n "$(frontend_dev_listeners)" ]]; then
      echo "WARN: Compile masih jalan. Tail log: tail -f $LOG_FILE" >&2
      echo "     Buka http://127.0.0.1:$FRONTEND_DEV_PORT/ setelah log menampilkan Ready / Compiled." >&2
    else
      echo "ERROR: Frontend tidak jalan. Lihat $LOG_FILE" >&2
      return 1
    fi
  else
    echo "Frontend HTTP ready."
  fi
  echo "FRONTEND_STARTED port=$FRONTEND_DEV_PORT log=$LOG_FILE"
}

frontend_stop() {
  frontend_dev_stop || true
  rm -f "$PID_FILE"
}

frontend_restart() {
  frontend_stop
  sleep 2
  frontend_start
}

frontend_status() {
  local pid
  pid="$(frontend_dev_listeners | head -1 || true)"
  if [[ -n "$pid" ]]; then
    echo "Frontend process: RUNNING pid=$pid port=$FRONTEND_DEV_PORT"
    curl -s -o /dev/null -w "GET / HTTP %{http_code}\n" "http://127.0.0.1:$FRONTEND_DEV_PORT/" || true
  else
    echo "Frontend process: STOPPED port=$FRONTEND_DEV_PORT"
  fi
}

cmd="${1:-start}"
case "$cmd" in
  start) frontend_start ;;
  stop) frontend_stop ;;
  restart) frontend_restart ;;
  status) frontend_status ;;
  logs) tail -f "$LOG_FILE" ;;
  -h | --help | help)
    cat <<EOF
Usage: $(basename "$0") <command>

Commands:
  start    Start Next.js dev on :3001 if not already healthy
  stop     Stop dev server listening on :3001 (this repo only)
  restart  stop → start
  status   Process + HTTP check
  logs     tail -f .tmp/frontend-3001.log
EOF
    ;;
  *)
    echo "Unknown command: ${cmd:-<none>}" >&2
    exit 1
    ;;
esac

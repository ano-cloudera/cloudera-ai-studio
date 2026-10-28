#!/usr/bin/env bash
# Canonical local frontend lifecycle (Next.js on :3001).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
# shellcheck source=../frontend/scripts/lib/frontend-dev-common.sh
source "$ROOT/frontend/scripts/lib/frontend-dev-common.sh"

LOG_FILE="${ROOT}/.tmp/frontend-3001.log"
PID_FILE="$FRONTEND_DIR/.next-dev.pid"

frontend_http_code() {
  curl -s -o /dev/null -w '%{http_code}' --connect-timeout 2 --max-time 8 "http://127.0.0.1:$FRONTEND_DEV_PORT/" 2>/dev/null || echo "000"
}

frontend_maybe_clean_stale_next() {
  if ! frontend_dev_check_log_stale "$LOG_FILE"; then
    echo "Removing stale frontend/.next (dev + production build conflict)…"
    rm -rf "$FRONTEND_DIR/.next"
  fi
}

frontend_start() {
  mkdir -p "${ROOT}/.tmp"
  local code
  code="$(frontend_http_code)"
  if [[ "$code" == "200" ]]; then
    if [[ -f "$FRONTEND_DIR/.env.local" ]] && grep -q 'Anywhere AI Studio' "$FRONTEND_DIR/.env.local"; then
      if curl -fsS --max-time 8 "http://127.0.0.1:$FRONTEND_DEV_PORT/" 2>/dev/null | grep -q 'Cloudera AI Studio'; then
        echo "Stale Cloudera bundle on :$FRONTEND_DEV_PORT — running restart-clean for hackathon branding…"
        frontend_restart_clean
        return $?
      fi
    fi
    echo "ALREADY_RUNNING port=$FRONTEND_DEV_PORT (HTTP 200)"
    return 0
  fi
  if [[ -n "$(frontend_dev_listeners)" ]]; then
    echo "Frontend on :$FRONTEND_DEV_PORT unhealthy (HTTP $code) — stopping…"
    frontend_stop
    frontend_maybe_clean_stale_next
  elif [[ "$code" == "500" ]]; then
    frontend_maybe_clean_stale_next
  fi
  if [[ ! -d "$FRONTEND_DIR/node_modules" ]]; then
    (cd "$FRONTEND_DIR" && npm install)
  fi
  echo "Starting Next.js on :$FRONTEND_DEV_PORT (log: $LOG_FILE)…"
  {
    echo "======== frontend start $(date -u +%Y-%m-%dT%H:%M:%SZ) ========"
  } >>"$LOG_FILE"
  # Background with exec (same pattern as frontend-clean-dev.sh) so the PID stays the next server.
  (
    cd "$FRONTEND_DIR"
    frontend_dev_load_env_files
    export BACKEND_API_URL="${BACKEND_API_URL:-http://127.0.0.1:8001}"
    export NEXT_PUBLIC_BACKEND_URL="${NEXT_PUBLIC_BACKEND_URL:-http://127.0.0.1:8001}"
    exec ./node_modules/.bin/next dev -H 0.0.0.0 -p "$FRONTEND_DEV_PORT"
  ) >>"$LOG_FILE" 2>&1 &
  echo $! >"$PID_FILE"
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

frontend_restart_clean() {
  frontend_stop
  sleep 1
  echo "Removing $FRONTEND_DIR/.next …"
  rm -rf "$FRONTEND_DIR/.next"
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
  restart-clean) frontend_restart_clean ;;
  status) frontend_status ;;
  logs) tail -f "$LOG_FILE" ;;
  -h | --help | help)
    cat <<EOF
Usage: $(basename "$0") <command>

Commands:
  start         Start Next.js dev on :3001 if not already healthy (HTTP 200)
  stop          Stop dev server listening on :3001 (this repo only)
  restart       stop → start
  restart-clean stop → rm .next → start (fix 500 / MODULE_NOT_FOUND)
  status        Process + HTTP check
  logs          tail -f .tmp/frontend-3001.log

Tip: never run "npm run build" while "next dev" is running — it corrupts .next.
EOF
    ;;
  *)
    echo "Unknown command: ${cmd:-<none>}" >&2
    exit 1
    ;;
esac

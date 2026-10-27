#!/usr/bin/env bash
# Shared helpers for frontend-dev lifecycle scripts (port 3001, scoped process stop).
set -euo pipefail

FRONTEND_DEV_PORT="${FRONTEND_DEV_PORT:-3001}"
FRONTEND_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
REPO_ROOT="$(cd "$FRONTEND_DIR/.." && pwd)"

STALE_CHUNK_PATTERNS='Cannot find module|MODULE_NOT_FOUND|ChunkLoadError|ENOENT.*\.next|missing server chunk'

frontend_dev_listeners() {
  lsof -nP -iTCP:"$FRONTEND_DEV_PORT" -sTCP:LISTEN -t 2>/dev/null || true
}

frontend_dev_process_cwd() {
  local pid="$1"
  lsof -a -p "$pid" -d cwd -Fn 2>/dev/null | sed -n 's/^n//p' | head -1
}

frontend_dev_is_our_listener() {
  local pid="$1"
  local cmd cwd
  cmd="$(ps -p "$pid" -o command= 2>/dev/null || true)"
  cwd="$(frontend_dev_process_cwd "$pid")"
  if [[ "$cwd" == "$FRONTEND_DIR"* ]]; then
    return 0
  fi
  if [[ "$cmd" == *next* ]] && [[ "$cmd" == *"$FRONTEND_DEV_PORT"* || "$cmd" == *"next dev"* ]]; then
    if [[ -n "$cwd" && ( "$cwd" == "$FRONTEND_DIR"* || "$cwd" == *"/frontend"* ) ]]; then
      return 0
    fi
  fi
  return 1
}

frontend_dev_stop() {
  local pid pids=() foreign=0
  while read -r pid; do
    [[ -z "$pid" ]] && continue
    if frontend_dev_is_our_listener "$pid"; then
      pids+=("$pid")
    else
      echo "ERROR: Port $FRONTEND_DEV_PORT is used by pid $pid (not frontend-dev). Stop it manually." >&2
      foreign=1
    fi
  done <<< "$(frontend_dev_listeners)"

  if [[ "$foreign" -eq 1 ]]; then
    return 1
  fi

  if [[ ${#pids[@]} -eq 0 ]]; then
    return 0
  fi

  echo "Stopping frontend-dev on :$FRONTEND_DEV_PORT (pids: ${pids[*]})…"
  for pid in "${pids[@]}"; do
    kill "$pid" 2>/dev/null || true
  done

  local i=0
  while [[ $i -lt 30 ]]; do
    if [[ -z "$(frontend_dev_listeners)" ]]; then
      echo "Port $FRONTEND_DEV_PORT released."
      return 0
    fi
    sleep 0.5
    i=$((i + 1))
  done

  echo "ERROR: Port $FRONTEND_DEV_PORT still in use after stop." >&2
  return 1
}

frontend_dev_wait_port() {
  local attempts="${1:-80}"
  local i=0
  while [[ $i -lt attempts ]]; do
    if [[ -n "$(frontend_dev_listeners)" ]]; then
      return 0
    fi
    sleep 0.25
    i=$((i + 1))
  done
  return 1
}

frontend_dev_wait_http() {
  local url="${1:-http://127.0.0.1:$FRONTEND_DEV_PORT/}"
  local attempts="${2:-240}"
  local i=0 code
  while [[ $i -lt attempts ]]; do
    # max-time: Next can accept TCP while compiling and hang the response without it.
    code="$(
      curl -s -o /dev/null -w '%{http_code}' --connect-timeout 2 --max-time 5 "$url" 2>/dev/null || true
    )"
    if [[ -n "$code" && "$code" != "000" ]]; then
      return 0
    fi
    sleep 0.5
    i=$((i + 1))
  done
  return 1
}

frontend_dev_wait_ready() {
  local url="${1:-http://127.0.0.1:$FRONTEND_DEV_PORT/}"
  frontend_dev_wait_port 80 || return 1
  frontend_dev_wait_http "$url" 240
}

frontend_dev_route_sweep() {
  local base="http://127.0.0.1:$FRONTEND_DEV_PORT"
  local paths=(/ /knowledge /prompts /skills /semantic-layer /connectors /usage /settings)
  local path code
  for path in "${paths[@]}"; do
    code="$(curl -s -o /dev/null -w '%{http_code}' "$base$path" || echo 000)"
    if [[ "$code" != "200" ]]; then
      echo "ROUTE_FAIL $path HTTP $code" >&2
      return 1
    fi
    echo "OK $path HTTP 200"
  done
  return 0
}

frontend_dev_proxy_health() {
  local base="http://127.0.0.1:$FRONTEND_DEV_PORT/api"
  local code
  code="$(curl -s -o /dev/null -w '%{http_code}' "$base/models" || echo 000)"
  if [[ "$code" == "200" ]]; then
    echo "OK /api/models HTTP 200"
    return 0
  fi
  if [[ "$code" == "502" || "$code" == "503" || "$code" == "000" ]]; then
    echo "BACKEND_NOT_READY: /api/models returned HTTP $code (backend may be down)." >&2
    return 2
  fi
  echo "PROXY_FAIL: /api/models HTTP $code" >&2
  return 1
}

frontend_dev_check_log_stale() {
  local logfile="$1"
  [[ -f "$logfile" ]] || return 0
  if grep -E "$STALE_CHUNK_PATTERNS" "$logfile" >/dev/null 2>&1; then
    echo "STALE_CHUNK detected in log:" >&2
    grep -E "$STALE_CHUNK_PATTERNS" "$logfile" | tail -5 >&2
    return 1
  fi
  return 0
}

frontend_dev_assert_dev_not_running() {
  local pid
  for pid in $(frontend_dev_listeners); do
    [[ -z "$pid" ]] && continue
    if frontend_dev_is_our_listener "$pid"; then
      echo "Frontend dev server is running on port $FRONTEND_DEV_PORT. Stop it before running production build." >&2
      echo "  Hint: $FRONTEND_DIR/scripts/frontend-clean-dev.sh --skip-build" >&2
      return 1
    fi
  done
  return 0
}

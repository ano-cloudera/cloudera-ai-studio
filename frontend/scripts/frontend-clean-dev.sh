#!/usr/bin/env bash
# Safe frontend-dev lifecycle: stop scoped dev → clean .next → (optional) build → dev on :3001 → health gates.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=lib/frontend-dev-common.sh
source "$SCRIPT_DIR/lib/frontend-dev-common.sh"

SKIP_BUILD=0
SKIP_START=0
DETACH=0
DO_BUILD=1
REPEAT=1
RUN_VALIDATION=1

usage() {
  cat <<EOF
Usage: $(basename "$0") [options]

  SIT pre-flight: stop dev, rm .next, npm run build, start dev, validate routes/proxy.

Options:
  --skip-build     Skip npm run build (faster dev-only restart)
  --no-start       Clean (and build) only; do not start dev
  --detach         Start dev in background (for run-dev-stack)
  --repeat N       Run stop/clean/start/validate cycle N times (default 1)
  --no-validate    Skip route/proxy checks after start
  -h, --help       Show this help

Never run 'npm run build' while 'next dev' is active on port $FRONTEND_DEV_PORT.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-build) SKIP_BUILD=1; DO_BUILD=0; shift ;;
    --no-start) SKIP_START=1; shift ;;
    --detach) DETACH=1; shift ;;
    --repeat) REPEAT="${2:-1}"; shift 2 ;;
    --no-validate) RUN_VALIDATION=0; shift ;;
    -h | --help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage; exit 1 ;;
  esac
done

LOG_FILE="${TMPDIR:-/tmp}/frontend-dev-${FRONTEND_DEV_PORT}.log"
PID_FILE="$FRONTEND_DIR/.next-dev.pid"

run_one_cycle() {
  local cycle="$1"
  echo "=== frontend-clean-dev cycle $cycle/$REPEAT ==="

  frontend_dev_stop

  echo "Removing $FRONTEND_DIR/.next …"
  rm -rf "$FRONTEND_DIR/.next"

  if [[ "$DO_BUILD" -eq 1 ]]; then
    frontend_dev_assert_dev_not_running
    echo "Running npm run build …"
    (cd "$FRONTEND_DIR" && npm run build)
  fi

  if [[ "$SKIP_START" -eq 1 ]]; then
    echo "Skip start (--no-start)."
    return 0
  fi

  : >"$LOG_FILE"
  echo "Starting next dev on :$FRONTEND_DEV_PORT (log: $LOG_FILE) …"
  (
    cd "$FRONTEND_DIR"
    frontend_dev_load_env_files
    export BACKEND_API_URL="${BACKEND_API_URL:-http://127.0.0.1:8001}"
    export NEXT_PUBLIC_BACKEND_URL="${NEXT_PUBLIC_BACKEND_URL:-http://127.0.0.1:8001}"
    export PORT="$FRONTEND_DEV_PORT"
    exec npm run dev -- -p "$FRONTEND_DEV_PORT"
  ) >>"$LOG_FILE" 2>&1 &
  local dev_pid=$!
  echo "$dev_pid" >"$PID_FILE"

  if [[ "$DETACH" -eq 1 && "$RUN_VALIDATION" -eq 0 ]]; then
    echo "Detached dev pid $dev_pid"
    return 0
  fi

  frontend_dev_wait_http "http://127.0.0.1:$FRONTEND_DEV_PORT/" 90

  if [[ "$RUN_VALIDATION" -eq 1 ]]; then
    frontend_dev_route_sweep
    set +e
    frontend_dev_proxy_health
    local proxy_rc=$?
    set -e
    if [[ "$proxy_rc" -eq 2 ]]; then
      echo "WARN: Backend not ready; frontend routes OK." >&2
    elif [[ "$proxy_rc" -ne 0 ]]; then
      return 1
    fi
    frontend_dev_check_log_stale "$LOG_FILE" || return 1
  fi

  if [[ "$DETACH" -eq 1 ]]; then
    echo "Dev server running (pid $dev_pid)."
  fi
  return 0
}

fail=0
c=1
while [[ $c -le "$REPEAT" ]]; do
  if ! run_one_cycle "$c"; then
    fail=1
    break
  fi
  if [[ "$c" -lt "$REPEAT" && "$SKIP_START" -eq 0 ]]; then
    echo "Preparing repeat: stopping for next cycle …"
    frontend_dev_stop
    sleep 1
  fi
  c=$((c + 1))
done

if [[ "$fail" -eq 0 ]]; then
  echo ""
  echo "M7D2 frontend-clean-dev: PASS"
  exit 0
fi

echo ""
echo "M7D2 frontend-clean-dev: FAIL"
exit 1

#!/usr/bin/env bash
# Canonical local backend lifecycle (FastAPI on 127.0.0.1:8001).
#
# Usage:
#   ./scripts/backend.sh start|stop|restart|status|logs
#
# Optional env override (not baked into launcher):
#   SEMANTIC_DEFAULT_MODEL_KEY=uat_commercial_p2_20261016 ./scripts/backend.sh start
#
# Do NOT start backend via ad-hoc nohup or pkill uvicorn globally.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=lib/backend-common.sh
source "$SCRIPT_DIR/lib/backend-common.sh"

cmd="${1:-}"
case "$cmd" in
  start)
    backend_start
    ;;
  stop)
    backend_stop
    ;;
  restart)
    backend_restart
    ;;
  status)
    backend_status
    ;;
  logs)
    backend_init_paths
    tail -f "$BACKEND_LOG_FILE"
    ;;
  -h | --help | help)
    cat <<EOF
Usage: $(basename "$0") <command>

Commands:
  start    Start backend if not already healthy on :8001
  stop     Stop backend owned by .tmp/backend-8001.pid only
  restart  stop → start with health checks
  status   PID, port, /health, /health/ready
  logs     tail -f .tmp/backend-8001.log

Environment loads (in order): deployment/profiles/runtime-closure.env, then .env
Exports: PYTHONPATH=backend, CORS_ORIGINS for :3001 (unless already set)

UAT/SIT may override SEMANTIC_DEFAULT_MODEL_KEY on the command line; it is not
hardcoded in this script.
EOF
    ;;
  *)
    echo "Unknown command: ${cmd:-<none>}" >&2
    echo "Run: $(basename "$0") --help" >&2
    exit 1
    ;;
esac

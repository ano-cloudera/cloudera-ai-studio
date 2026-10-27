#!/usr/bin/env bash
# Shared backend lifecycle (port 8001, PID ownership under .tmp/).
set -euo pipefail

BACKEND_PORT="${BACKEND_PORT:-8001}"
BACKEND_HOST="${BACKEND_HOST:-127.0.0.1}"

backend_repo_root() {
  local here
  here="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
  echo "$here"
}

backend_init_paths() {
  BACKEND_ROOT="$(backend_repo_root)"
  BACKEND_PID_FILE="${BACKEND_PID_FILE:-$BACKEND_ROOT/.tmp/backend-8001.pid}"
  BACKEND_LOG_FILE="${BACKEND_LOG_FILE:-$BACKEND_ROOT/.tmp/backend-8001.log}"
  mkdir -p "$BACKEND_ROOT/.tmp"
}

backend_load_env() {
  backend_init_paths
  cd "$BACKEND_ROOT"

  if [[ "${CAI_DEPLOYMENT_PRESERVE_ENV:-}" == "1" ]]; then
    export PYTHONPATH="${BACKEND_ROOT}/backend${PYTHONPATH:+:${PYTHONPATH}}"
    return 0
  fi

  if [[ ! -x "$BACKEND_ROOT/.venv/bin/python" ]]; then
    echo "ERROR: missing $BACKEND_ROOT/.venv/bin/python — run scripts/bootstrap/bootstrap-local.sh" >&2
    return 1
  fi

  if [[ -f "$BACKEND_ROOT/deployment/profiles/runtime-closure.env" ]]; then
    set -a
    # shellcheck disable=SC1091
    source "$BACKEND_ROOT/deployment/profiles/runtime-closure.env"
    set +a
  fi

  if [[ -f "$BACKEND_ROOT/.env" ]]; then
    set -a
    # shellcheck disable=SC1091
    source "$BACKEND_ROOT/.env"
    set +a
  fi

  export PYTHONPATH="${BACKEND_ROOT}/backend${PYTHONPATH:+:${PYTHONPATH}}"
  export CORS_ORIGINS="${CORS_ORIGINS:-http://127.0.0.1:3001,http://localhost:3001}"

  # Local CAI simulation: keep SQLite metadata paths after .env (Postgres dev defaults).
  if [[ "${CAI_SIM_METADATA:-}" == "1" ]]; then
    [[ -n "${CAI_SIM_DATABASE_URL:-}" ]] && export DATABASE_URL="$CAI_SIM_DATABASE_URL"
    [[ -n "${CAI_SIM_DOCUMENT_STORAGE_ROOT:-}" ]] && export DOCUMENT_STORAGE_ROOT="$CAI_SIM_DOCUMENT_STORAGE_ROOT"
    [[ -n "${CAI_SIM_SEMANTIC_RUNTIME_STORAGE_ROOT:-}" ]] && export SEMANTIC_RUNTIME_STORAGE_ROOT="$CAI_SIM_SEMANTIC_RUNTIME_STORAGE_ROOT"
    export STATE_STORE=sqlite
    export UVICORN_WORKERS="${UVICORN_WORKERS:-1}"
  fi
}

backend_port_listener_pids() {
  lsof -nP -iTCP:"$BACKEND_PORT" -sTCP:LISTEN -t 2>/dev/null | tr '\n' ' ' || true
}

backend_read_pid_file() {
  backend_init_paths
  if [[ ! -f "$BACKEND_PID_FILE" ]]; then
    echo ""
    return 0
  fi
  tr -d '[:space:]' <"$BACKEND_PID_FILE"
}

backend_pid_alive() {
  local pid="$1"
  [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null
}

backend_is_owned_uvicorn() {
  local pid="$1"
  local cmd
  cmd="$(ps -p "$pid" -o command= 2>/dev/null || true)"
  [[ "$cmd" == *uvicorn* ]] && [[ "$cmd" == *app.main:app* ]] && [[ "$cmd" == *backend* || "$cmd" == *"--app-dir backend"* ]]
}

backend_http_code() {
  local path="$1"
  curl -sf -o /dev/null -w '%{http_code}' "http://${BACKEND_HOST}:${BACKEND_PORT}${path}" 2>/dev/null || echo "000"
}

backend_health_ok() {
  [[ "$(backend_http_code /health)" == "200" ]]
}

backend_ready_ok() {
  backend_health_ok && curl -sf "http://${BACKEND_HOST}:${BACKEND_PORT}/health/ready" >/dev/null 2>&1
}

backend_clean_stale_pid_file() {
  backend_init_paths
  local pid
  pid="$(backend_read_pid_file)"
  [[ -z "$pid" ]] && return 0
  if ! backend_pid_alive "$pid"; then
    rm -f "$BACKEND_PID_FILE"
  fi
}

backend_log_startup_header() {
  backend_init_paths
  {
    echo "======== backend start $(date -u +%Y-%m-%dT%H:%M:%SZ) pid_file=$BACKEND_PID_FILE ========"
  } >>"$BACKEND_LOG_FILE"
}

backend_wait_port_release() {
  local i=0
  while [[ $i -lt 40 ]]; do
    [[ -z "$(backend_port_listener_pids)" ]] && return 0
    sleep 0.25
    i=$((i + 1))
  done
  return 1
}

backend_start_process() {
  backend_init_paths
  backend_load_env
  backend_log_startup_header

  local workers="${UVICORN_WORKERS:-1}"
  nohup "$BACKEND_ROOT/.venv/bin/python" -m uvicorn app.main:app \
    --app-dir backend \
    --host "$BACKEND_HOST" \
    --port "$BACKEND_PORT" \
    --workers "$workers" \
    >>"$BACKEND_LOG_FILE" 2>&1 </dev/null &
  local pid=$!
  echo "$pid" >"$BACKEND_PID_FILE"
  disown "$pid" 2>/dev/null || true
  echo "$pid"
}

backend_wait_healthy() {
  local pid="$1"
  local attempts="${2:-60}"
  local i=0
  while [[ $i -lt attempts ]]; do
    if ! backend_pid_alive "$pid"; then
      return 2
    fi
    if backend_ready_ok; then
      return 0
    fi
    sleep 0.5
    i=$((i + 1))
  done
  return 1
}

backend_start() {
  backend_init_paths
  backend_clean_stale_pid_file

  if backend_ready_ok; then
    local listeners
    listeners="$(backend_port_listener_pids)"
    listeners="${listeners%% }"
    if [[ -n "$listeners" ]]; then
      echo "ALREADY_RUNNING"
      echo "PID=${listeners%% *}"
      echo "PORT=$BACKEND_PORT"
      echo "HEALTH=PASS"
      return 0
    fi
  fi

  local listeners pid_file_pid
  listeners="$(backend_port_listener_pids)"
  listeners="${listeners%% }"
  if [[ -n "$listeners" ]]; then
    for pid in $listeners; do
      if ! backend_is_owned_uvicorn "$pid"; then
        echo "ERROR: port $BACKEND_PORT held by non-repo process pid=$pid" >&2
        return 1
      fi
    done
    if backend_ready_ok; then
      echo "ALREADY_RUNNING"
      echo "PID=${listeners%% *}"
      echo "PORT=$BACKEND_PORT"
      echo "HEALTH=PASS"
      return 0
    fi
    echo "ERROR: port $BACKEND_PORT in use but /health/ready not OK" >&2
    return 1
  fi

  pid_file_pid="$(backend_read_pid_file)"
  if [[ -n "$pid_file_pid" ]] && backend_pid_alive "$pid_file_pid"; then
    echo "ERROR: stale ownership pid=$pid_file_pid alive but not listening on $BACKEND_PORT" >&2
    return 1
  fi
  rm -f "$BACKEND_PID_FILE"

  local pid
  pid="$(backend_start_process)"

  if backend_wait_healthy "$pid"; then
    echo "BACKEND_STARTED"
    echo "PID=$pid"
    echo "PORT=$BACKEND_PORT"
    echo "HEALTH=PASS"
    return 0
  fi

  echo "BACKEND_START_FAILED"
  if ! backend_pid_alive "$pid"; then
    echo "Process $pid exited during startup." >&2
  else
    echo "Timed out waiting for /health/ready." >&2
  fi
  tail -100 "$BACKEND_LOG_FILE" >&2 || true
  rm -f "$BACKEND_PID_FILE"
  return 1
}

backend_stop() {
  backend_init_paths
  local pid
  pid="$(backend_read_pid_file)"

  if [[ -z "$pid" ]]; then
    echo "Backend: STOPPED (no pid file)"
    backend_wait_port_release || true
    return 0
  fi

  if ! backend_pid_alive "$pid"; then
    rm -f "$BACKEND_PID_FILE"
    echo "Backend: STOPPED (removed stale pid file)"
    backend_wait_port_release || true
    return 0
  fi

  echo "Stopping backend pid=$pid (SIGTERM)…"
  kill -TERM "$pid" 2>/dev/null || true

  local i=0
  while [[ $i -lt 30 ]]; do
    if ! backend_pid_alive "$pid"; then
      break
    fi
    sleep 0.5
    i=$((i + 1))
  done

  if backend_pid_alive "$pid"; then
    echo "Sending SIGKILL to pid=$pid…"
    kill -KILL "$pid" 2>/dev/null || true
    sleep 1
  fi

  rm -f "$BACKEND_PID_FILE"
  if backend_wait_port_release; then
    echo "Backend: STOPPED"
    return 0
  fi
  echo "WARN: port $BACKEND_PORT may still be in use" >&2
  return 1
}

backend_restart() {
  backend_stop || true
  backend_wait_port_release || true
  sleep 1
  backend_start
}

backend_status() {
  backend_init_paths
  backend_clean_stale_pid_file
  local pid_file_pid listeners health ready ready_body core_ready
  pid_file_pid="$(backend_read_pid_file)"
  listeners="$(backend_port_listener_pids)"
  listeners="${listeners%% }"

  local proc_state="STOPPED"
  if [[ -n "$pid_file_pid" ]] && backend_pid_alive "$pid_file_pid"; then
    proc_state="RUNNING"
  elif [[ -n "$listeners" ]]; then
    proc_state="RUNNING (foreign pid file)"
  fi

  local port_state="NOT LISTENING"
  if [[ -n "$listeners" ]]; then
    port_state="LISTENING"
  fi

  health="$(backend_http_code /health)"
  if backend_ready_ok; then
    ready="200"
    ready_body="$(curl -sf "http://${BACKEND_HOST}:${BACKEND_PORT}/health/ready" 2>/dev/null || echo '{}')"
  else
    ready="000"
    ready_body="{}"
  fi

  core_ready="unknown"
  if command -v python3 >/dev/null 2>&1; then
    core_ready="$(printf '%s' "$ready_body" | python3 -c 'import json,sys
try:
  d=json.load(sys.stdin)
  print(str(d.get("core_ready", d.get("ready", "unknown"))).lower())
except Exception:
  print("unknown")' 2>/dev/null || echo "unknown")"
  fi

  echo "Backend process: $proc_state"
  echo "PID: ${pid_file_pid:-—}"
  echo "Port $BACKEND_PORT: $port_state"
  echo "/health: $health"
  echo "/health/ready: $ready"
  echo "core_ready: $core_ready"

  if [[ "$health" == "200" && "$ready" == "200" && "$port_state" == "LISTENING" ]]; then
    return 0
  fi
  return 1
}

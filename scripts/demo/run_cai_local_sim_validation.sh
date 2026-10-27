#!/usr/bin/env bash
# Run CAI local sim validation gates (backend must stay up for duration).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
EV="$ROOT/testing/evidence/cai-local-sim-validation"
mkdir -p "$EV"
DB="$ROOT/runtime/cai-sim/metadata/studio.db"
SQLITE_URL="sqlite+pysqlite:///${DB}"

cd "$ROOT"
./scripts/dev-cai-sim-backend.sh stop 2>/dev/null || true
sleep 1
./scripts/dev-cai-sim-backend.sh start | tee "$EV/backend-start.log"

export CAI_SIM_METADATA=1
export CAI_SIM_DATABASE_URL="$SQLITE_URL"
export DATABASE_URL="$SQLITE_URL"
export GOLDEN_BANKING_DATABASE_URL="$SQLITE_URL"
export GOLDEN_BANKING_RUN_INTEGRATION=1

"$ROOT/.venv/bin/python" - <<PY | tee "$EV/runtime-config.json"
import json, urllib.request
from pathlib import Path
root = Path("$ROOT")
sim = root / "runtime/cai-sim"
with urllib.request.urlopen("http://127.0.0.1:8001/health/ready", timeout=15) as r:
    ready = json.loads(r.read())
with urllib.request.urlopen("http://127.0.0.1:8001/health", timeout=15) as r:
    health = json.loads(r.read())
print(json.dumps({
    "sqlite_path": str(sim / "metadata" / "studio.db"),
    "documents": str(sim / "documents"),
    "semantic": str(sim / "semantic"),
    "UVICORN_WORKERS": "${UVICORN_WORKERS:-1}",
    "DATABASE_URL": "$SQLITE_URL",
    "health": health,
    "ready": ready,
    "metadata_database": ready.get("components", {}).get("metadata_database"),
    "core_ready": ready.get("core_ready"),
}, indent=2))
PY

"$ROOT/.venv/bin/python" "$ROOT/scripts/demo/register_banking_connector.py" 2>&1 | tee "$EV/register-banking-connector.log"
"$ROOT/.venv/bin/python" "$ROOT/scripts/demo/register_banking_knowledge.py" 2>&1 | tee "$EV/register-banking-knowledge.log"

"$ROOT/.venv/bin/python" "$ROOT/scripts/demo/golden_path_banking_phase1_gate.py" 2>&1 | tee "$EV/phase1-gate.log"
P1="${PIPESTATUS[0]}"
"$ROOT/.venv/bin/python" "$ROOT/scripts/demo/golden_path_banking_phase2_knowledge_gate.py" 2>&1 | tee "$EV/phase2-gate.log"
P2="${PIPESTATUS[0]}"

"$ROOT/.venv/bin/python" "$ROOT/scripts/demo/cai_local_sim_validation.py" 2>&1 | tee "$EV/validation-helper.log"

# Restart persistence
"$ROOT/.venv/bin/python" - "$ROOT" > "$EV/persistence-before-restart.json" <<'PY'
import json, sqlite3, sys
from pathlib import Path
root = Path(sys.argv[1])
db = root / "runtime/cai-sim/metadata/studio.db"
con = sqlite3.connect(db)
cur = con.cursor()
snap = {}
for t in ("conversations","messages","prompts","skills","connectors","libraries","documents","usage_events"):
    try:
        cur.execute(f"SELECT COUNT(*) FROM {t}")
        snap[t] = cur.fetchone()[0]
    except Exception:
        snap[t] = None
con.close()
print(json.dumps({"phase": "before", "counts": snap}, indent=2))
PY

./scripts/dev-cai-sim-backend.sh stop
sleep 2
./scripts/dev-cai-sim-backend.sh start | tee -a "$EV/backend-restart.log"
sleep 2

"$ROOT/.venv/bin/python" - "$ROOT" > "$EV/persistence-after-restart.json" <<'PY'
import json, sqlite3, sys
from pathlib import Path
root = Path(sys.argv[1])
db = root / "runtime/cai-sim/metadata/studio.db"
con = sqlite3.connect(db)
cur = con.cursor()
snap = {}
for t in ("conversations","messages","prompts","skills","connectors","libraries","documents","usage_events"):
    try:
        cur.execute(f"SELECT COUNT(*) FROM {t}")
        snap[t] = cur.fetchone()[0]
    except Exception:
        snap[t] = None
con.close()
print(json.dumps({"phase": "after", "counts": snap}, indent=2))
PY

# Knowledge recovery evidence (integration test against live stack)
cd "$ROOT/backend" && PYTHONPATH=. DATABASE_URL="$SQLITE_URL" \
  "$ROOT/.venv/bin/pytest" tests/test_knowledge_ingestion_recovery.py -q -m integration 2>&1 | tee "$EV/knowledge-recovery-tests.log"
KR="${PIPESTATUS[0]}"

cd "$ROOT" && make test-backend 2>&1 | tee "$EV/backend-pytest.log" | tail -3
BT="${PIPESTATUS[0]}"
cd "$ROOT/frontend" && npm run test -- --run 2>&1 | tee "$EV/frontend-vitest.log" | tail -3
FT="${PIPESTATUS[0]}"
npm run build 2>&1 | tee "$EV/frontend-build.log" | tail -3
FB="${PIPESTATUS[0]}"

# Postgres alembic head check (dev URL from .env if present)
set +u
# shellcheck disable=SC1091
[[ -f "$ROOT/.env" ]] && source "$ROOT/.env"
set -u
if [[ -n "${DATABASE_URL:-}" ]] && [[ "${DATABASE_URL}" == postgresql* ]]; then
  (cd "$ROOT/backend" && DATABASE_URL="${DATABASE_URL}" "$ROOT/.venv/bin/alembic" current 2>&1 | tee "$EV/postgres-alembic-current.log") || true
fi

{
  echo "phase1_gate=$P1"
  echo "phase2_gate=$P2"
  echo "knowledge_recovery_tests=$KR"
  echo "backend_pytest=$BT"
  echo "frontend_vitest=$FT"
  echo "frontend_build=$FB"
} | tee "$EV/gate-summary.txt"

exit 0

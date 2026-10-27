#!/usr/bin/env bash
# Non-destructive standalone isolation audit (does NOT move/rename enterprise-ai-poc).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OLD="/Users/triano/Documents/Works/cloudera/enterprise-ai-poc"
EVID="$ROOT/testing/evidence/standalone/ISOLATION"
PY="$ROOT/.venv/bin/python"
mkdir -p "$EVID"

if [[ ! -x "$PY" ]]; then
  echo "Missing $PY — run scripts/bootstrap/bootstrap-local.sh" >&2
  exit 1
fi
if grep -q "enterprise-ai-poc" "$ROOT/.venv/pyvenv.cfg" 2>/dev/null; then
  echo "Refusing: .venv pyvenv.cfg still references source monorepo. Re-run bootstrap." >&2
  exit 1
fi
py_real="$(readlink -f "$PY" 2>/dev/null || true)"
if [[ "$py_real" == *"enterprise-ai-poc"* ]]; then
  echo "Refusing: .venv python resolves into source monorepo ($py_real)." >&2
  exit 1
fi

{
  echo "audit_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "standalone_root=$ROOT"
  echo "source_monorepo=$OLD"
  echo "method=non_destructive_path_and_process_audit"
} | tee "$EVID/proof-meta.txt"

cd "$ROOT"
./scripts/dev-backend.sh start | tee "$EVID/backend-start.log"
./scripts/dev-backend.sh status | tee "$EVID/backend-status.txt"

if ! curl -sf "http://127.0.0.1:8001/health" >/dev/null; then
  echo "ISOLATION_AUDIT_BLOCKED: backend health failed" | tee "$EVID/result.txt"
  exit 1
fi

cd "$ROOT/backend"
PYTHONPATH=. "$PY" -m pytest -q tests/test_stores_factory.py tests/test_chat_api.py | tee "$EVID/pytest-sample.log"

"$PY" - <<'PY' | tee "$EVID/sys-path-audit.txt"
import os
import sys
from pathlib import Path

root = Path("/Users/triano/Documents/Works/cloudera/cloudera-ai-studio")
bad = [p for p in sys.path if any(x in p for x in ("enterprise-ai-poc", "backend-dev", "frontend-dev"))]
print("bad_sys_path", bad)
print("cwd", os.getcwd())
print("standalone_backend", root / "backend")
PY

block=0
while read -r pid; do
  [[ -z "$pid" ]] && continue
  cwd="$(lsof -a -p "$pid" -d cwd -Fn 2>/dev/null | sed -n 's/^n//p' | head -1)"
  if [[ "$cwd" == *"enterprise-ai-poc"* && "$cwd" != *"cloudera-ai-studio"* ]]; then
    echo "WARN: listener pid=$pid cwd=$cwd" | tee -a "$EVID/process-cwd-warn.txt"
    block=1
  fi
done < <(lsof -nP -iTCP:8001 -sTCP:LISTEN -t 2>/dev/null; lsof -nP -iTCP:3001 -sTCP:LISTEN -t 2>/dev/null || true)

if [[ "$block" -eq 1 ]]; then
  echo "ISOLATION_AUDIT_BLOCKED: stack listener cwd under source monorepo" | tee "$EVID/result.txt"
  exit 1
fi

echo "ISOLATION_AUDIT_PASS_NON_DESTRUCTIVE" | tee "$EVID/result.txt"
echo "NOTE: Full unavailable-path proof is disabled; see docs/migration/SOURCE_EXTRACTION_POLICY.md" | tee -a "$EVID/result.txt"

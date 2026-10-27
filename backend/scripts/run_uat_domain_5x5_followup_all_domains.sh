#!/usr/bin/env bash
# Run follow-up UAT per domain (resumable) then merge reports.
set -euo pipefail
BE="$(cd "$(dirname "$0")/.." && pwd)"
BASE="${1:-http://127.0.0.1:8000}"
PROVIDER="${2:-gemini}"
EXTRA_ARGS=("${@:3}")
PY="${BE}/../.venv/bin/python"
DOMAINS=(sales b2b stock_tempo stock_sat sat_oos service_level picking unloading promo cross_domain)

cd "$BE"
export PYTHONPATH="$BE"
LOG="${BE}/eval/uat_domain_5x5_followup_latest.log"
: >"$LOG"
REPORTS=()
for d in "${DOMAINS[@]}"; do
  echo "=== domain: $d ===" | tee -a "$LOG"
  tmp="$(mktemp)"
  set +e
  PYTHONUNBUFFERED=1 "$PY" scripts/run_uat_domain_5x5_followup.py "$BASE" "$PROVIDER" --domain="$d" "${EXTRA_ARGS[@]}" 2>&1 | tee -a "$LOG" | tee "$tmp"
  set -e
  rep="$(python3 -c "import json,sys; d=json.loads(sys.stdin.read().splitlines()[-1]); print(d.get('report',''))" < "$tmp" 2>/dev/null || true)"
  rm -f "$tmp"
  if [[ -n "$rep" && -f "$rep" ]]; then
    REPORTS+=("$rep")
  fi
done
if ((${#REPORTS[@]})); then
  "$PY" scripts/merge_uat_domain_5x5_followup_reports.py "${REPORTS[@]}"
else
  echo "No per-domain reports captured" >&2
  exit 1
fi

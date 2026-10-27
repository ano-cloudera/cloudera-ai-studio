#!/usr/bin/env bash
# Canonical SIT pre-flight: clean .next, production build, dev on :3001, validate.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
"$ROOT/frontend/scripts/frontend-clean-dev.sh" "$@"
"$ROOT/frontend/scripts/frontend-clean-dev.sh" --skip-build --repeat 2

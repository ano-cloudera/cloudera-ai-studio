#!/usr/bin/env bash
# Production build only when frontend dev is not listening on :3001.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=lib/frontend-dev-common.sh
source "$SCRIPT_DIR/lib/frontend-dev-common.sh"

frontend_dev_assert_dev_not_running
cd "$FRONTEND_DIR"
exec npm run build

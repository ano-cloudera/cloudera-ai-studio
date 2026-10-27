#!/usr/bin/env bash
# Smoke-check Next.js /api rewrites against a running dev server (default :3001).
set -euo pipefail
BASE="${1:-http://127.0.0.1:3001/api}"
curl -sf -o /dev/null "$BASE/health" && echo "OK /api/health"
curl -sf -o /dev/null "$BASE/health/ready" && echo "OK /api/health/ready"
curl -sf -o /dev/null "$BASE/version" && echo "OK /api/version"
curl -sf -o /dev/null "$BASE/models" && echo "OK /api/models"
curl -sf -o /dev/null "$BASE/v1/libraries" && echo "OK /api/v1/libraries"
echo "Proxy route gate passed."

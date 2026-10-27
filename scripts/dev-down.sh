#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
"$ROOT/scripts/dev-frontend.sh" stop
"$ROOT/scripts/dev-backend.sh" stop
echo "Studio dev stack stopped (Docker Postgres/Qdrant left running)."

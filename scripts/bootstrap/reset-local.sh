#!/usr/bin/env bash
# LOCAL ONLY — destructive reset of runtime artifacts (not PostgreSQL).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

echo "WARNING: This removes local runtime data under backend/runtime and backend/var."
echo "It does NOT drop PostgreSQL. Press Ctrl+C to abort, Enter to continue."
read -r _

rm -rf "$ROOT/backend/runtime/document_storage"/*
rm -rf "$ROOT/backend/var/semantic-runtime"/*
rm -f "$ROOT/backend/runtime/"*.sqlite "$ROOT/backend/runtime/"*.duckdb 2>/dev/null || true
mkdir -p "$ROOT/backend/runtime/document_storage" "$ROOT/backend/var/semantic-runtime"
echo "Local runtime artifacts cleared."

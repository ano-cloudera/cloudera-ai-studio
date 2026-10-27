#!/usr/bin/env bash
# Initialize Backend persistent storage layout under CAI_DATA_DIR (NFS mount target).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
DATA="${CAI_DATA_DIR:?CAI_DATA_DIR is required}"

if [[ "$DATA" != /* ]]; then
  DATA="$ROOT/$DATA"
fi

mkdir -p \
  "$DATA/metadata" \
  "$DATA/documents" \
  "$DATA/attachments" \
  "$DATA/exports" \
  "$DATA/logs" \
  "$DATA/var/semantic-runtime"

for dir in "$DATA/metadata" "$DATA/documents" "$DATA/var/semantic-runtime"; do
  if [[ ! -w "$dir" ]]; then
    echo "ERROR: not writable: $dir" >&2
    exit 1
  fi
done

echo "CAI storage initialized at $DATA"
echo "  metadata/          MUST PERSIST (SQLite studio.db when used)"
echo "  documents/         MUST PERSIST"
echo "  attachments/       MUST PERSIST"
echo "  var/semantic-runtime/ MUST PERSIST"
echo "  exports/           TEMPORARY / regenerable"
echo "  logs/              OPTIONAL (prefer stdout in CAI)"

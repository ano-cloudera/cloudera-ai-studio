#!/usr/bin/env bash
# Download the embedding model to NFS (run once from a CAI Session; the Application never downloads).
# Usage: bash scripts/cai/prepare_embedding_model.sh [destination]
set -euo pipefail
dest="${1:-/home/cdsw/models/bge-m3}"
repo="${EMBEDDING_REPO:-BAAI/bge-m3}"
mkdir -p "$dest"
python3 - "$repo" "$dest" <<'PY'
import sys
from huggingface_hub import snapshot_download

repo, dest = sys.argv[1:3]
snapshot_download(repo_id=repo, local_dir=dest, allow_patterns=["*.json", "*.txt", "*.model", "*.safetensors", "1_Pooling/*", "modules.json"])
PY
test -f "$dest/config.json" || { echo "config.json missing in $dest" >&2; exit 1; }
echo "Embedding model ready → $dest (set EMBEDDING_MODEL=$dest, HF_HUB_OFFLINE=1)"

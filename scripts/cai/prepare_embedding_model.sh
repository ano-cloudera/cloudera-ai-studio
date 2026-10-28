#!/usr/bin/env bash
# Download the embedding model to NFS (run once from a CAI Session; the Application never downloads).
# Needs the backend venv (sentence-transformers + huggingface_hub): bash scripts/cai/prepare_venvs.sh backend
# Usage: bash scripts/cai/prepare_embedding_model.sh [destination]
set -euo pipefail
dest="${1:-/home/cdsw/models/bge-m3}"
repo="${EMBEDDING_REPO:-BAAI/bge-m3}"
py="${PYTHON:-/home/cdsw/.venvs/studio-backend/bin/python}"
mkdir -p "$dest"
"$py" - "$repo" "$dest" <<'PY'
import sys
from huggingface_hub import snapshot_download

repo, dest = sys.argv[1:3]
# bge-m3 ships weights as pytorch_model.bin (no safetensors); skip the ONNX copy and images.
snapshot_download(repo_id=repo, local_dir=dest, ignore_patterns=["onnx/*", "imgs/*", "*.jpg", "*.webp", "*.md", "long.jpg"])
PY
test -f "$dest/config.json" || { echo "config.json missing in $dest" >&2; exit 1; }
ls "$dest"/pytorch_model.bin "$dest"/model.safetensors >/dev/null 2>&1 || { echo "no model weights in $dest" >&2; exit 1; }
HF_HUB_OFFLINE=1 "$py" - "$dest" <<'PY'
import sys
from sentence_transformers import SentenceTransformer

model = SentenceTransformer(sys.argv[1])
vec = model.encode(["embedding smoke test"])
print("load OK, dimension =", vec.shape[1])
PY
echo "Embedding model ready → $dest (set EMBEDDING_MODEL=$dest, HF_HUB_OFFLINE=1)"

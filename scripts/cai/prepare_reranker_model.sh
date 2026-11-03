#!/usr/bin/env bash
# Download the reranker model (optional; run from a CAI Session or the AMP setup job when ENABLE_RERANKER is true).
# Needs the backend venv (sentence-transformers + huggingface_hub): bash scripts/cai/prepare_venvs.sh backend
# Usage: bash scripts/cai/prepare_reranker_model.sh [destination]
set -euo pipefail
unset PYTHONPATH   # CAI addon site-packages must not leak into the venv
dest="${1:-/home/cdsw/models/bge-reranker-v2-m3}"
repo="${RERANKER_REPO:-BAAI/bge-reranker-v2-m3}"
py="${PYTHON:-/home/cdsw/.venvs/studio-backend/bin/python}"
mkdir -p "$dest"
"$py" - "$repo" "$dest" <<'PY'
import sys
from huggingface_hub import snapshot_download

repo, dest = sys.argv[1:3]
snapshot_download(repo_id=repo, local_dir=dest, ignore_patterns=["*.md", "onnx/*", "imgs/*", "*.jpg", "*.webp"])
PY
test -f "$dest/config.json" || { echo "config.json missing in $dest" >&2; exit 1; }
if [ ! -f "$dest/pytorch_model.bin" ] && [ ! -f "$dest/model.safetensors" ]; then
  echo "no model weights in $dest" >&2
  exit 1
fi
HF_HUB_OFFLINE=1 "$py" - "$dest" <<'PY'
import sys
from sentence_transformers import CrossEncoder

model = CrossEncoder(sys.argv[1])
scores = model.predict([("delivery time", "Regular delivery has a service level of 4 days."), ("delivery time", "Opened beauty products are not returnable.")])
print("load OK, relevant scores higher than irrelevant:", float(scores[0]) > float(scores[1]))
PY
echo "Reranker ready → $dest (set RERANKER_PROVIDER=bge and RERANKER_MODEL=$dest, HF_HUB_OFFLINE=1)"

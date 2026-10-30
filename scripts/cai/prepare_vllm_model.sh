#!/usr/bin/env bash
# Download model weights for the optional vLLM Application to the project filesystem
# (run once from a Session or the AMP setup job; the Application cannot download).
# Needs the backend venv (huggingface_hub): bash scripts/cai/prepare_venvs.sh backend
# Usage: VLLM_MODEL_ID=<org/name> bash scripts/cai/prepare_vllm_model.sh [destination]
# Gated models also need HUGGING_FACE_HUB_TOKEN.
set -euo pipefail
unset PYTHONPATH   # CAI addon site-packages must not leak into the venv
repo="${VLLM_MODEL_ID:?set VLLM_MODEL_ID to the Hugging Face model id, for example org/model-name}"
dest="${1:-/home/cdsw/models/${repo##*/}}"
py="${PYTHON:-/home/cdsw/.venvs/studio-backend/bin/python}"
mkdir -p "$dest"
"$py" - "$repo" "$dest" <<'PY'
import sys
from huggingface_hub import snapshot_download

repo, dest = sys.argv[1:3]
snapshot_download(repo_id=repo, local_dir=dest, ignore_patterns=["*.md", "original/*", "*.gguf"])
PY
test -f "$dest/config.json" || { echo "config.json missing in $dest" >&2; exit 1; }
echo "Model ready → $dest (set MODEL_PATH=$dest on the vLLM Application)"

#!/usr/bin/env bash
# Create one virtualenv per Application type on the project filesystem (run once from a Session).
# Applications start in /home/cdsw and use these venvs through PYTHON_EXECUTABLE.
# Usage: bash scripts/cai/prepare_venvs.sh [backend|vllm|all]
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
VENVS="${VENVS_DIR:-/home/cdsw/.venvs}"
export PIP_USER=false
PIPFLAGS=(--no-user --retries 10 --timeout 60)
target="${1:-all}"

make_venv() {
  local name="$1"
  python -m venv "$VENVS/$name"
  "$VENVS/$name/bin/python" -m pip install "${PIPFLAGS[@]}" --upgrade pip
}

if [ "$target" = backend ] || [ "$target" = all ]; then
  make_venv studio-backend
  "$VENVS/studio-backend/bin/python" -m pip install "${PIPFLAGS[@]}" -r "$ROOT/backend/requirements.txt"
  "$VENVS/studio-backend/bin/python" -m pip check
  echo "Backend venv ready → $VENVS/studio-backend (PYTHON_EXECUTABLE=$VENVS/studio-backend/bin/python)"
fi

if [ "$target" = vllm ] || [ "$target" = all ]; then
  make_venv studio-vllm
  # Pins follow the BNI-validated L40S profile; vllm 0.29.0 did not bring in the extras below.
  "$VENVS/studio-vllm/bin/python" -m pip install "${PIPFLAGS[@]}" "vllm==${VLLM_VERSION:-0.29.0}" \
    PyYAML packaging requests certifi urllib3 cachetools cloudpickle
  "$VENVS/studio-vllm/bin/python" -m pip check
  "$VENVS/studio-vllm/bin/python" -c "import torch, vllm; print(torch.__version__, torch.version.cuda, vllm.__version__, 'cuda_available=', torch.cuda.is_available())"
  echo "vLLM venv ready → $VENVS/studio-vllm (run from a GPU Session to see cuda_available=True; stop that Session before starting the vLLM Application)"
fi

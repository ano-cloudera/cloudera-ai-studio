#!/usr/bin/env bash
# Download Qdrant binary for CAI (run once from Session; Application does not download).
# Usage: bash scripts/cai/prepare_qdrant_binary.sh [destination]
set -euo pipefail
dest="${1:-/home/cdsw/tools/qdrant/qdrant}"
version="${QDRANT_VERSION:-1.12.5}"
arch="$(uname -m)"
case "$arch" in
  x86_64) asset="qdrant-x86_64-unknown-linux-gnu" ;;
  aarch64|arm64) asset="qdrant-aarch64-unknown-linux-gnu" ;;
  *) echo "Unsupported arch: $arch" >&2; exit 1 ;;
esac
url="${QDRANT_BINARY_URL:-https://github.com/qdrant/qdrant/releases/download/v${version}/${asset}.tar.gz}"
mkdir -p "$(dirname "$dest")"
tmp="$(mktemp -d)"
curl -fsSL "$url" | tar -xz -C "$tmp"
bin="$(find "$tmp" -name qdrant -type f | head -1)"
install -m 755 "$bin" "$dest"
echo "Installed Qdrant $version → $dest"

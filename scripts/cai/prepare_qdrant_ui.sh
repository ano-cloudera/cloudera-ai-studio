#!/usr/bin/env bash
# Install the official Qdrant Web UI next to the Qdrant binary (run once from a Session).
# The Application serves it at /dashboard on the same port as the API (no extra port needed).
# Usage: bash scripts/cai/prepare_qdrant_ui.sh [static_dir]
set -euo pipefail
dest="${1:-/home/cdsw/tools/qdrant/static}"
version="${QDRANT_WEB_UI_VERSION:-v0.2.20}"
sha256="${QDRANT_WEB_UI_SHA256:-331d6f83ee3c0e771a02b80ec58df3857e7ebab99b7cbdd1a15be205a9215d3d}"
url="${QDRANT_WEB_UI_URL:-https://github.com/qdrant/qdrant-web-ui/releases/download/${version}/dist-qdrant.zip}"
tmp="$(mktemp -d)"
curl -fsSL -o "$tmp/ui.zip" "$url"
actual="$(sha256sum "$tmp/ui.zip" 2>/dev/null | cut -d' ' -f1 || shasum -a 256 "$tmp/ui.zip" | cut -d' ' -f1)"
if [ "$actual" != "$sha256" ]; then
  echo "Checksum mismatch for $url (expected $sha256, got $actual). Set QDRANT_WEB_UI_SHA256 for a different version." >&2
  exit 1
fi
unzip -q "$tmp/ui.zip" -d "$tmp/unz"
rm -rf "$dest"
mkdir -p "$dest"
cp -r "$tmp/unz/dist/"* "$dest/"
test -f "$dest/index.html" || { echo "index.html missing in $dest" >&2; exit 1; }
echo "Qdrant Web UI $version → $dest (open <qdrant-app-url>/dashboard)"

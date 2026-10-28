#!/usr/bin/env bash
# Install Node.js (CAI Sessions and Applications ship without it) — run once from a Session.
# The frontend launcher puts $NODE_HOME/bin on PATH, so set NODE_HOME=<dest> on the Application.
# Usage: bash scripts/cai/prepare_node.sh [destination]
set -euo pipefail
dest="${1:-/home/cdsw/tools/node}"
version="${NODE_VERSION:-v20.20.2}"
case "$(uname -m)" in
  x86_64) arch=x64; sha="${NODE_SHA256:-df770b2a6f130ed8627c9782c988fda9669fa23898329a61a871e32f965e007d}" ;;
  aarch64|arm64) arch=arm64; sha="${NODE_SHA256:-73093db209e4e9e09dd7d15a47aeaab1b74833830df03efa5f942a1122c5fa71}" ;;
  *) echo "Unsupported arch: $(uname -m)" >&2; exit 1 ;;
esac
url="${NODE_URL:-https://nodejs.org/dist/${version}/node-${version}-linux-${arch}.tar.xz}"
tmp="$(mktemp -d)"
curl -fsSL -o "$tmp/node.tar.xz" "$url"
actual="$(sha256sum "$tmp/node.tar.xz" | cut -d' ' -f1)"
if [ "$actual" != "$sha" ]; then
  echo "Checksum mismatch for $url (expected $sha, got $actual). Set NODE_SHA256 for a different version." >&2
  exit 1
fi
rm -rf "$dest"
mkdir -p "$dest"
tar -xJf "$tmp/node.tar.xz" -C "$dest" --strip-components=1
"$dest/bin/node" --version
"$dest/bin/npm" --version
echo "Node ready → $dest (export PATH=$dest/bin:\$PATH; Application env: NODE_HOME=$dest)"

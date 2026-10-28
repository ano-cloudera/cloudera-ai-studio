#!/usr/bin/env python3
"""Minimal Qdrant collections UI on CDSW_READONLY_PORT."""
from __future__ import annotations

import argparse
import json
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer


def fetch_collections(qdrant_url: str) -> dict:
    url = qdrant_url.rstrip("/") + "/collections"
    with urllib.request.urlopen(url, timeout=5) as resp:  # noqa: S310
        return json.loads(resp.read().decode("utf-8"))


class Handler(BaseHTTPRequestHandler):
    qdrant_url: str = "http://127.0.0.1:6333"

    def do_GET(self) -> None:  # noqa: N802
        try:
            data = fetch_collections(self.qdrant_url)
            names = [c.get("name") for c in (data.get("result") or {}).get("collections") or []]
            body = (
                "<html><head><title>Qdrant UI</title></head><body>"
                "<h1>Qdrant collections</h1><ul>"
                + "".join(f"<li>{n}</li>" for n in names)
                + "</ul></body></html>"
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(body)
        except OSError as exc:
            msg = f"<pre>Qdrant unreachable: {exc}</pre>".encode("utf-8")
            self.send_response(503)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(msg)

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--qdrant-url", default="http://127.0.0.1:6333")
    parser.add_argument("--port", type=int, required=True)
    args = parser.parse_args()
    Handler.qdrant_url = args.qdrant_url
    server = HTTPServer(("127.0.0.1", args.port), Handler)
    server.serve_forever()


if __name__ == "__main__":
    main()

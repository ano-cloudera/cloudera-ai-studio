#!/usr/bin/env python3
"""Minimal HTTP MCP-style demo server for local / CAI sidecar testing."""
from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, HTTPServer


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return

    def do_POST(self) -> None:  # noqa: N802
        if not self.path.startswith("/tools/"):
            self.send_response(404)
            self.end_headers()
            return
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            body = {}
        tool = self.path.rsplit("/", 1)[-1]
        payload = {
            "tool": tool,
            "echo": body.get("question") or body.get("message") or "",
            "status": "ok",
        }
        data = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def main() -> None:
    import os

    host = os.environ.get("MCP_DEMO_HOST", "127.0.0.1")
    port = int(os.environ.get("MCP_DEMO_PORT", "8765"))
    server = HTTPServer((host, port), Handler)
    print(f"MCP HTTP demo listening on http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()

"""Serve the API only under a secret path prefix, so an Application without a platform login is not open to everyone.

The Frontend proxies the browser's calls to `<backend-url>/<token>/...`; the browser never sees the token. Anything else,
except the liveness check, is answered with 404. With no token configured (local development) nothing changes.
"""
from __future__ import annotations

import hmac

OPEN_PATHS = frozenset({"/health"})


class PathTokenMiddleware:
    def __init__(self, app, token: str, open_paths: frozenset[str] = OPEN_PATHS) -> None:
        self.app = app
        self.token = token.encode()
        self.prefix = f"/{token}"
        self.open_paths = open_paths

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return
        path = scope["path"]
        if path in self.open_paths:
            await self.app(scope, receive, send)
            return
        first, _, rest = path[1:].partition("/")
        if hmac.compare_digest(first.encode(), self.token):
            inner = "/" + rest
            scope = {**scope, "path": inner, "raw_path": inner.encode(), "root_path": self.prefix}
            await self.app(scope, receive, send)
            return
        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 1008})
            return
        body = b'{"detail":"Not Found"}'
        await send({"type": "http.response.start", "status": 404, "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]})
        await send({"type": "http.response.body", "body": body})

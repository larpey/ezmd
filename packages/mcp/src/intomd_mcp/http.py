"""intomd_mcp.http: the streamable HTTP transport behind a bearer-token check (docs/spec/part1.md 8.4).

The token is checked on every HTTP request with a constant-time comparison before the MCP app sees it.
The legacy SSE transport is deliberately not offered (deprecated in the MCP specification).
"""

from __future__ import annotations

import hmac
import json
from typing import Any

from starlette.types import ASGIApp, Receive, Scope, Send

__all__ = ["BearerAuth", "build_http_app"]


class BearerAuth:
    """ASGI middleware: `Authorization: Bearer <token>` required on every HTTP request."""

    def __init__(self, app: ASGIApp, token: str | None) -> None:
        self.app = app
        self._token = token.encode("utf-8") if token else None

    def _authorized(self, scope: Scope) -> bool:
        if self._token is None:
            return True
        for name, value in scope.get("headers", []):
            if name == b"authorization":
                scheme, _, credential = value.partition(b" ")
                if scheme.lower() == b"bearer" and hmac.compare_digest(credential.strip(), self._token):
                    return True
        return False

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or self._authorized(scope):
            await self.app(scope, receive, send)
            return
        body = json.dumps(
            {"error": {"code": "unauthorized", "message": "A valid bearer token is required.", "status": 401}}
        ).encode("utf-8")
        await send(
            {
                "type": "http.response.start",
                "status": 401,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode("ascii")),
                    (b"www-authenticate", b'Bearer realm="intomd-mcp"'),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})


def build_http_app(server: Any, *, token: str | None, host: str = "127.0.0.1", path: str = "/mcp") -> ASGIApp:
    """The streamable HTTP ASGI app for `server` (an MCPServer), wrapped in BearerAuth. Embedders (the API
    container mounts it at `/mcp`) may pass `token=None` when their own middleware authenticates."""
    app: ASGIApp = server.streamable_http_app(streamable_http_path=path, host=host)
    return BearerAuth(app, token)

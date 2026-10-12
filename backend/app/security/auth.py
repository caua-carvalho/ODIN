"""Optional bearer-token authentication for the Odin API.

Disabled by default (``ODIN_API_TOKEN`` empty). When a token is configured,
every request to ``/api/*`` (except ``/api/health``) must present it either as
an ``Authorization: Bearer <token>`` header or — for WebSocket connections,
which browsers/RN cannot set headers on — via the ``?token=<token>`` query
parameter.

Registration order matters: in ``main.py`` this middleware is added *before*
``CORSMiddleware``. Starlette makes the **last**-added middleware the outermost
one, so adding CORS afterwards keeps it outside the auth gate and lets it answer
preflight ``OPTIONS`` requests (which never carry an ``Authorization`` header).
"""
from __future__ import annotations

import json
import secrets
from urllib.parse import unquote

from starlette.types import ASGIApp, Receive, Scope, Send

# WebSocket close code for policy violation.
_WS_POLICY_VIOLATION = 1008


def _extract_bearer(headers: dict[bytes, bytes]) -> bytes | None:
    auth = headers.get(b"authorization", b"")
    prefix = b"Bearer "
    if auth.startswith(prefix):
        return auth[len(prefix):].strip()
    return None


def _extract_query_token(query_string: bytes) -> bytes | None:
    if b"token=" not in query_string:
        return None
    for part in query_string.split(b"&"):
        if part.startswith(b"token="):
            raw = part[len(b"token="):].decode()
            return unquote(raw).encode()
    return None


class TokenAuthMiddleware:
    """Rejects /api/* requests that lack the configured bearer token."""

    def __init__(self, app: ASGIApp, token: str) -> None:
        self.app = app
        self.expected = token.encode() if token else b""

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if not self.expected or scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if not path.startswith("/api") or path == "/api/health":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers") or [])
        provided = _extract_bearer(headers)
        if provided is None:
            provided = _extract_query_token(scope.get("query_string", b""))

        if provided is None or not secrets.compare_digest(provided, self.expected):
            if scope["type"] == "websocket":
                await send(
                    {
                        "type": "websocket.close",
                        "code": _WS_POLICY_VIOLATION,
                        "reason": "unauthorized",
                    }
                )
                return
            await self._send_unauthorized(send)
            return

        await self.app(scope, receive, send)

    async def _send_unauthorized(self, send) -> None:
        body = json.dumps({"detail": "Unauthorized"}).encode()
        await send(
            {
                "type": "http.response.start",
                "status": 401,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})
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
import time
from urllib.parse import unquote

from starlette.types import ASGIApp, Receive, Scope, Send

# WebSocket close code for policy violation.
_WS_POLICY_VIOLATION = 1008

# HTTP status for a throttled client.
_HTTP_TOO_MANY_REQUESTS = 429


def _client_key(scope: Scope) -> str:
    """Best-effort client identity for throttling.

    Prefers ``CF-Connecting-IP`` / ``X-Forwarded-For`` so that, behind the
    Cloudflare tunnel (where every request arrives from 127.0.0.1), distinct
    clients are still bucketed separately. Falls back to the socket peer.
    """
    headers = {k.lower(): v for k, v in (scope.get("headers") or [])}
    for header in (b"cf-connecting-ip", b"x-forwarded-for"):
        raw = headers.get(header)
        if raw:
            return raw.decode("latin-1").split(",")[0].strip()
    client = scope.get("client")
    if client:
        return client[0]
    return "unknown"


class _FailureLimiter:
    """In-memory sliding-window counter of failed auth attempts per client."""

    def __init__(self, max_failures: int, window_seconds: int) -> None:
        self.max_failures = max(1, max_failures)
        self.window = max(1, window_seconds)
        # key -> list of failure timestamps (monotonic)
        self._hits: dict[str, list[float]] = {}

    def is_blocked(self, key: str) -> bool:
        self._prune(key)
        return len(self._hits.get(key, ())) >= self.max_failures

    def record_failure(self, key: str) -> None:
        self._hits.setdefault(key, []).append(time.monotonic())
        self._prune(key)

    def reset(self, key: str) -> None:
        self._hits.pop(key, None)

    def _prune(self, key: str) -> None:
        cutoff = time.monotonic() - self.window
        hits = self._hits.get(key)
        if not hits:
            return
        hits[:] = [t for t in hits if t >= cutoff]
        if not hits:
            self._hits.pop(key, None)


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

    def __init__(
        self,
        app: ASGIApp,
        token: str,
        limiter: _FailureLimiter | None = None,
    ) -> None:
        self.app = app
        self.expected = token.encode() if token else b""
        self.limiter = limiter

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if not self.expected or scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if not path.startswith("/api") or path == "/api/health":
            await self.app(scope, receive, send)
            return

        key = _client_key(scope)
        if self.limiter is not None and self.limiter.is_blocked(key):
            await self._reject_throttled(scope, send)
            return

        headers = dict(scope.get("headers") or [])
        provided = _extract_bearer(headers)
        if provided is None:
            provided = _extract_query_token(scope.get("query_string", b""))

        if provided is None or not secrets.compare_digest(provided, self.expected):
            if self.limiter is not None:
                self.limiter.record_failure(key)
            if scope["type"] == "websocket":
                await send(
                    {
                        "type": "websocket.close",
                        "code": _WS_POLICY_VIOLATION,
                        "reason": "unauthorized",
                    }
                )
                return
            await self._send_json(send, 401, {"detail": "Unauthorized"})
            return

        if self.limiter is not None:
            self.limiter.reset(key)

        await self.app(scope, receive, send)

    async def _reject_throttled(self, scope: Scope, send: Send) -> None:
        if scope["type"] == "websocket":
            await send(
                {
                    "type": "websocket.close",
                    "code": _WS_POLICY_VIOLATION,
                    "reason": "too many attempts",
                }
            )
            return
        await self._send_json(
            send,
            429,
            {"detail": "Too many failed authentication attempts. Try again later."},
        )

    async def _send_json(self, send: Send, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode()
        await send(
            {
                "type": "http.response.start",
                "status": status,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})
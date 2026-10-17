"""Optional bearer authentication for the Odin API.

Disabled by default (``ODIN_API_TOKEN`` empty). When a token is configured,
every request to ``/api/*`` (except the public paths below) must present a
credential either as an ``Authorization: Bearer <credential>`` header or — for
WebSocket connections, which browsers/RN cannot set headers on — via the
``?token=<credential>`` query parameter.

Two kinds of credential are accepted:

* the raw ``ODIN_API_TOKEN`` (used by the CLI and the mobile app), and
* a signed, expiring **session token** issued by ``POST /api/auth/login`` (used
  by the web panel so it never stores the raw token — see
  ``app/security/session.py``).

Registration order matters: in ``main.py`` this middleware is added *before*
``CORSMiddleware``. Starlette makes the **last**-added middleware the outermost
one, so adding CORS afterwards keeps it outside the auth gate and lets it answer
preflight ``OPTIONS`` requests (which never carry an ``Authorization`` header).

CSRF (issue #15): CSRF does **not** apply to the current design, because the
credential is never carried automatically by the browser — it travels in an
``Authorization: Bearer`` header (or the ``?token=`` WebSocket query parameter),
which a cross-site form/img/script cannot set. There are no cookies and no
cookie-based session, so an attacker page has no ambient authority to abuse.
CSRF would only become applicable if authentication moved to cookies
(``SameSite=None`` ``HttpOnly`` session cookies): at that point this project
would need anti-CSRF tokens (``SameSite`` + double-submit or a synchronizer
token) on every state-changing ``/api/*`` route. This note is the recorded
decision; revisit it if cookie auth is ever introduced.
"""
from __future__ import annotations

import ipaddress
import json
import secrets
import time
from urllib.parse import unquote

from starlette.types import ASGIApp, Receive, Scope, Send

from app.security.session import SessionSigner

# WebSocket close code for policy violation.
_WS_POLICY_VIOLATION = 1008

# HTTP status for a throttled client.
_HTTP_TOO_MANY_REQUESTS = 429

# Paths reachable without a credential: the health probe (clients test
# connectivity with it) and the login endpoint itself (it *issues* credentials
# and authenticates the raw token from the request body).
PUBLIC_PATHS = frozenset({"/api/health", "/api/auth/login"})


def _is_loopback_peer(host: object) -> bool:
    """True when ``host`` names a loopback address.

    The backend is intended to sit behind a *local* Cloudflare tunnel (or an
    equivalent reverse proxy) listening on ``127.0.0.1``, so a request whose
    immediate socket peer is loopback really did come from that proxy. Handles
    ``localhost``, IPv4/IPv6 literals, bracketed IPv6 and the
    ``::ffff:127.0.0.1`` mapped form; anything unparseable (e.g. the
    ``testclient`` peer) is not loopback.
    """
    if not isinstance(host, str):
        return False
    value = host.strip()
    if value.startswith("[") and value.endswith("]"):
        value = value[1:-1]
    # Drop an IPv6 zone id (e.g. ``fe80::1%eth0``).
    value = value.split("%", 1)[0]
    if not value:
        return False
    if value.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(value).is_loopback
    except ValueError:
        return False


def _client_key(scope: Scope) -> str:
    """Best-effort client identity for throttling.

    ``CF-Connecting-IP`` / ``X-Forwarded-For`` are honoured **only** when the
    immediate socket peer is loopback (issue #15): the intended topology puts a
    local tunnel/proxy on ``127.0.0.1`` in front of the backend, so a loopback
    peer is genuinely the proxy and those headers carry the real client. From any
    other peer the headers are attacker-controlled — trusting them would let a
    client rotate its rate-limit bucket on every attempt — so the socket address
    is used instead.
    """
    client = scope.get("client")
    peer = client[0] if client else None
    if _is_loopback_peer(peer):
        headers = {k.lower(): v for k, v in (scope.get("headers") or [])}
        for header in (b"cf-connecting-ip", b"x-forwarded-for"):
            raw = headers.get(header)
            if raw:
                candidate = raw.decode("latin-1").split(",")[0].strip()
                if candidate:
                    return candidate
    return peer or "unknown"


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


def bearer_from_header(authorization: str | None) -> str | None:
    """Return the credential from an ``Authorization: Bearer <x>`` header."""
    if not authorization:
        return None
    prefix = "Bearer "
    if authorization.startswith(prefix):
        return authorization[len(prefix):].strip() or None
    return None


def token_from_query(query_string: str | None) -> str | None:
    """Return the ``?token=<x>`` credential (WebSocket fallback), if present."""
    if not query_string:
        return None
    for part in query_string.split("&"):
        if part.startswith("token="):
            value = unquote(part[len("token="):]).strip()
            return value or None
    return None


def extract_credential(authorization: str | None, query_string: str | None) -> str | None:
    """Resolve the credential a client presented (header first, then query)."""
    return bearer_from_header(authorization) or token_from_query(query_string)


class TokenAuthMiddleware:
    """Rejects /api/* requests that lack a valid credential."""

    def __init__(
        self,
        app: ASGIApp,
        token: str,
        limiter: _FailureLimiter | None = None,
        session_signer: SessionSigner | None = None,
    ) -> None:
        self.app = app
        self.expected = token.encode() if token else b""
        self.limiter = limiter
        self.session_signer = session_signer

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if not self.expected or scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        # Tolerate a trailing slash so e.g. /api/health/ is not gated either.
        if not path.startswith("/api") or path.rstrip("/") in PUBLIC_PATHS:
            await self.app(scope, receive, send)
            return

        key = _client_key(scope)
        if self.limiter is not None and self.limiter.is_blocked(key):
            await self._reject_throttled(scope, send)
            return

        headers = dict(scope.get("headers") or [])
        provided = extract_credential(
            headers.get(b"authorization", b"").decode("latin-1"),
            (scope.get("query_string") or b"").decode("latin-1"),
        )

        if provided is None or not self._is_authorized(provided):
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

    def _is_authorized(self, credential: str) -> bool:
        """Accept the raw API token or a currently-valid session token."""
        if secrets.compare_digest(credential.encode("utf-8"), self.expected):
            return True
        if self.session_signer is not None:
            return self.session_signer.verify(credential) is not None
        return False

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
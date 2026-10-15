"""Signed, expiring session tokens for the web panel login.

The panel authenticates once with the long-lived ``ODIN_API_TOKEN`` (see
``POST /api/auth/login``) and receives a signed *session* token that it stores
in ``localStorage``. Session tokens are accepted anywhere the raw API token is
(``Authorization: Bearer`` header or ``?token=`` for WebSockets), so the rest of
the system is unchanged.

The token is an HMAC-SHA256 over a small JSON payload — no third-party
dependency (no PyJWT) and no server-side session store, which keeps hosting
stateless. Format::

    <base64url(payload-json)>.<base64url(hmac)>

The payload is ``{"alg": "odin-session-v1", "sub": ..., "iat": ..., "exp": ...,
"jti": ...}``. Because the payload is signed (not encrypted) it only carries
non-secret data: an expiry and a random id.

The signing secret is ``ODIN_SESSION_SECRET`` when set, otherwise it falls back
to ``ODIN_API_TOKEN`` (so no extra configuration is required to get started).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from functools import lru_cache

from app.config import settings

# Bump to invalidate every previously issued session token.
ALGORITHM_LABEL = "odin-session-v1"


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64url_decode(value: str) -> bytes:
    # Restore the padding stripped by ``_b64url_encode``.
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _sign(secret: bytes, signing_input: bytes) -> bytes:
    return hmac.new(secret, signing_input, hashlib.sha256).digest()


class SessionSigner:
    """Creates and verifies stateless HMAC-signed session tokens."""

    def __init__(self, secret: str) -> None:
        if not secret:
            raise ValueError("session secret must not be empty")
        self._secret = secret.encode("utf-8")

    def create(
        self,
        ttl_seconds: int,
        subject: str = "panel",
        now: int | None = None,
    ) -> tuple[str, int]:
        """Return ``(token, expires_at)`` where ``expires_at`` is a unix time."""
        issued = int(time.time()) if now is None else int(now)
        expires_at = issued + max(1, int(ttl_seconds))
        payload = {
            "alg": ALGORITHM_LABEL,
            "sub": subject,
            "iat": issued,
            "exp": expires_at,
            "jti": secrets.token_urlsafe(8),
        }
        encoded = _b64url_encode(
            json.dumps(payload, separators=(",", ":")).encode("utf-8")
        )
        signature = _b64url_encode(_sign(self._secret, encoded.encode("ascii")))
        return f"{encoded}.{signature}", expires_at

    def verify(self, token: str, now: int | None = None) -> int | None:
        """Return the unix expiry if ``token`` is a valid, unexpired session.

        Returns ``None`` for anything malformed, tampered with, signed by a
        different secret, or past its expiry.
        """
        if not token or "." not in token:
            return None
        encoded, _, signature = token.partition(".")
        expected = _b64url_encode(_sign(self._secret, encoded.encode("ascii")))
        if not hmac.compare_digest(signature, expected):
            return None
        try:
            payload = json.loads(_b64url_decode(encoded))
        except (ValueError, json.JSONDecodeError):
            return None
        if not isinstance(payload, dict) or payload.get("alg") != ALGORITHM_LABEL:
            return None
        expires_at = payload.get("exp")
        if not isinstance(expires_at, int):
            return None
        current = int(time.time()) if now is None else int(now)
        if expires_at < current:
            return None
        return expires_at


@lru_cache
def get_session_signer() -> SessionSigner | None:
    """Shared signer, or ``None`` when authentication is disabled.

    Authentication is disabled when neither ``ODIN_SESSION_SECRET`` nor
    ``ODIN_API_TOKEN`` is configured. Call ``get_session_signer.cache_clear()``
    after changing settings (e.g. in tests).
    """
    secret = settings.odin_session_secret or settings.odin_api_token
    if not secret:
        return None
    return SessionSigner(secret)

"""Web panel login.

The panel exchanges the long-lived ``ODIN_API_TOKEN`` for a signed, expiring
*session* token (see ``app/security/session.py``). The raw token is only sent
once, in the login request body; afterwards the panel presents the session token
as a bearer credential, so the long-lived secret never has to be kept in
``localStorage``.

``/api/auth/login`` is exempt from the auth middleware (it issues credentials
instead of requiring them), so it enforces its own failure rate limit.
"""

from __future__ import annotations

import logging
import secrets

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.config import settings
from app.security.auth import _FailureLimiter, _client_key, extract_credential
from app.security.session import get_session_signer

logger = logging.getLogger("odin.api.auth")

router = APIRouter()

# Login is a public endpoint (no credential yet), so it cannot rely on the
# middleware's limiter — guard against token brute force here.
_login_limiter = _FailureLimiter(
    max_failures=settings.odin_auth_max_failures,
    window_seconds=settings.odin_auth_window_seconds,
)


class LoginRequest(BaseModel):
    token: str = Field(..., min_length=1)
    # "Remember me": 7 days when true (ODIN_SESSION_TTL_DAYS), else a shorter
    # session (ODIN_SESSION_TTL_HOURS).
    remember: bool = True


class LoginResponse(BaseModel):
    token: str
    expires_at: int
    ttl_seconds: int


class SessionResponse(BaseModel):
    authenticated: bool
    # "session" when a signed session token was presented, "token" for the raw
    # API token (which has no expiry of its own).
    method: str
    expires_at: int | None = None


@router.post("/login", response_model=LoginResponse)
async def login(payload: LoginRequest, request: Request) -> LoginResponse:
    """Validate the API token and mint a time-limited session token."""
    signer = get_session_signer()
    if signer is None or not settings.odin_api_token:
        raise HTTPException(status_code=503, detail="Authentication is not enabled")

    key = _client_key(request.scope)
    if _login_limiter.is_blocked(key):
        raise HTTPException(
            status_code=429,
            detail="Too many failed login attempts. Try again later.",
        )

    if not secrets.compare_digest(
        payload.token.encode("utf-8"), settings.odin_api_token.encode("utf-8")
    ):
        _login_limiter.record_failure(key)
        logger.warning("Failed login attempt from %s", key)
        raise HTTPException(status_code=401, detail="Invalid token")

    _login_limiter.reset(key)

    ttl_seconds = (
        max(1, settings.odin_session_ttl_days) * 86400
        if payload.remember
        else max(1, settings.odin_session_ttl_hours) * 3600
    )
    token, expires_at = signer.create(ttl_seconds)
    logger.info("Issued a web panel session valid until %s", expires_at)
    return LoginResponse(token=token, expires_at=expires_at, ttl_seconds=ttl_seconds)


@router.get("/session", response_model=SessionResponse)
async def session_status(request: Request) -> SessionResponse:
    """Describe the credential that authenticated this request.

    Only reachable once the middleware accepted the credential, so the panel
    uses it to check whether a stored session is still valid on boot.
    """
    credential = extract_credential(
        request.headers.get("authorization"), request.url.query
    )
    signer = get_session_signer()
    expires_at: int | None = None
    if signer is not None and credential:
        expires_at = signer.verify(credential)
    return SessionResponse(
        authenticated=True,
        method="session" if expires_at is not None else "token",
        expires_at=expires_at,
    )

"""Security tests - signed login sessions (web panel auth).

Covers the stateless session tokens minted by ``POST /api/auth/login`` and the
middleware that accepts them alongside the raw ``ODIN_API_TOKEN``.
"""
import os
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

# Make sure we can import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))
os.environ.setdefault("GEMINI_API_KEY", "test-key")

from app.config import settings
from app.security import session as session_module
from app.security.auth import TokenAuthMiddleware, _FailureLimiter
from app.security.session import SessionSigner

RAW_TOKEN = "correct-horse-battery-staple"


class TestSessionSigner:
    def test_roundtrip(self):
        signer = SessionSigner("s3cret")
        token, expires_at = signer.create(3600, now=1_700_000_000)
        assert expires_at == 1_700_003_600
        assert signer.verify(token, now=1_700_000_100) == expires_at

    def test_expired(self):
        signer = SessionSigner("s3cret")
        token, expires_at = signer.create(60, now=1_700_000_000)
        assert signer.verify(token, now=expires_at + 1) is None
        # Boundary: still valid exactly at expiry.
        assert signer.verify(token, now=expires_at) == expires_at

    def test_wrong_secret(self):
        token, _ = SessionSigner("s3cret").create(3600)
        assert SessionSigner("other").verify(token) is None

    def test_tampered_payload(self):
        signer = SessionSigner("s3cret")
        token, _ = signer.create(3600)
        payload, _, signature = token.partition(".")
        assert signer.verify(f"{payload}x.{signature}") is None

    def test_garbage_and_empty(self):
        signer = SessionSigner("s3cret")
        for value in ("", "not-a-token", "a.b.c", "...."):
            assert signer.verify(value) is None

    def test_empty_secret_rejected(self):
        with pytest.raises(ValueError):
            SessionSigner("")


@pytest.fixture
def signer_client(monkeypatch):
    """A minimal app guarded by the real middleware + login router."""
    monkeypatch.setattr(settings, "odin_api_token", RAW_TOKEN)
    monkeypatch.setattr(settings, "odin_session_secret", "")
    monkeypatch.setattr(settings, "odin_session_ttl_days", 7)
    monkeypatch.setattr(settings, "odin_session_ttl_hours", 12)
    session_module.get_session_signer.cache_clear()

    from app.api.routes import auth as auth_routes

    auth_routes._login_limiter.reset("testclient")
    app = FastAPI()
    app.include_router(auth_routes.router, prefix="/api/auth")

    @app.get("/api/secret")
    async def secret():
        return {"ok": True}

    @app.get("/api/health")
    async def health():
        return {"status": "online"}

    app.add_middleware(
        TokenAuthMiddleware,
        token=RAW_TOKEN,
        limiter=_FailureLimiter(10, 60),
        session_signer=session_module.get_session_signer(),
    )

    with TestClient(app) as client:
        yield client

    session_module.get_session_signer.cache_clear()
    auth_routes._login_limiter.reset("testclient")


def _login(client: TestClient, token: str = RAW_TOKEN, remember: bool = True):
    return client.post("/api/auth/login", json={"token": token, "remember": remember})


class TestLoginEndpoint:
    def test_valid_token_issues_session(self, signer_client):
        response = _login(signer_client)
        assert response.status_code == 200
        body = response.json()
        assert body["ttl_seconds"] == 7 * 86400
        assert body["expires_at"] > 0

    def test_remember_false_is_short_session(self, signer_client):
        response = _login(signer_client, remember=False)
        assert response.status_code == 200
        assert response.json()["ttl_seconds"] == 12 * 3600

    def test_wrong_token_rejected(self, signer_client):
        assert _login(signer_client, token="nope").status_code == 401

    def test_session_token_is_accepted(self, signer_client):
        session_token = _login(signer_client).json()["token"]
        ok = signer_client.get(
            "/api/secret", headers={"Authorization": f"Bearer {session_token}"}
        )
        assert ok.status_code == 200

    def test_raw_token_still_accepted(self, signer_client):
        ok = signer_client.get(
            "/api/secret", headers={"Authorization": f"Bearer {RAW_TOKEN}"}
        )
        assert ok.status_code == 200

    def test_query_parameter_accepted(self, signer_client):
        session_token = _login(signer_client).json()["token"]
        ok = signer_client.get(f"/api/secret?token={session_token}")
        assert ok.status_code == 200

    def test_missing_credential_rejected(self, signer_client):
        assert signer_client.get("/api/secret").status_code == 401

    def test_health_is_public(self, signer_client):
        assert signer_client.get("/api/health").status_code == 200

    def test_session_status_reports_expiry(self, signer_client):
        session_token = _login(signer_client).json()["token"]
        body = signer_client.get(
            "/api/auth/session", headers={"Authorization": f"Bearer {session_token}"}
        ).json()
        assert body["authenticated"] is True
        assert body["method"] == "session"
        assert body["expires_at"] is not None

    def test_session_status_with_raw_token(self, signer_client):
        body = signer_client.get(
            "/api/auth/session", headers={"Authorization": f"Bearer {RAW_TOKEN}"}
        ).json()
        assert body["method"] == "token"
        assert body["expires_at"] is None

    def test_expired_session_rejected_by_middleware(self, signer_client):
        expired, _ = SessionSigner(RAW_TOKEN).create(60, now=1_700_000_000)
        response = signer_client.get(
            "/api/secret", headers={"Authorization": f"Bearer {expired}"}
        )
        assert response.status_code == 401


class TestDisabledAuth:
    def test_public_when_no_token(self):
        async def secret(request):
            return JSONResponse({"ok": True})

        app = FastAPI()
        app.add_middleware(TokenAuthMiddleware, token="")
        app.router.routes.append(Route("/api/secret", secret))
        with TestClient(app) as client:
            assert client.get("/api/secret").status_code == 200

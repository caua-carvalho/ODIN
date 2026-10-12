"""Tests for the hosting-oriented security gate.

Covers:
- the exposure guard that refuses a non-loopback bind without a token;
- the failed-token rate limiter used by TokenAuthMiddleware.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.security.auth import _FailureLimiter, _client_key


class TestExposureGuard:
    def _guard(self, monkeypatch, host, token):
        from app import main as main_mod
        from app.config import settings

        monkeypatch.setattr(settings, "odin_host", host)
        monkeypatch.setattr(settings, "odin_api_token", token)
        return main_mod._enforce_exposure_guard

    def test_loopback_without_token_is_allowed(self, monkeypatch):
        guard = self._guard(monkeypatch, "127.0.0.1", "")
        guard()  # should not raise

    def test_localhost_without_token_is_allowed(self, monkeypatch):
        guard = self._guard(monkeypatch, "localhost", "")
        guard()

    def test_public_bind_without_token_is_refused(self, monkeypatch):
        guard = self._guard(monkeypatch, "0.0.0.0", "")
        with pytest.raises(RuntimeError, match="Refusing to start"):
            guard()

    def test_public_bind_with_token_is_allowed(self, monkeypatch):
        guard = self._guard(monkeypatch, "0.0.0.0", "secret")
        guard()


class TestClientKey:
    def test_prefers_cf_connecting_ip(self):
        scope = {
            "headers": [(b"cf-connecting-ip", b"1.2.3.4")],
            "client": ("127.0.0.1", 1234),
        }
        assert _client_key(scope) == "1.2.3.4"

    def test_falls_back_to_x_forwarded_for(self):
        scope = {
            "headers": [(b"x-forwarded-for", b"5.6.7.8, 9.9.9.9")],
            "client": ("127.0.0.1", 1234),
        }
        assert _client_key(scope) == "5.6.7.8"

    def test_falls_back_to_socket_peer(self):
        scope = {"headers": [], "client": ("10.0.0.9", 1234)}
        assert _client_key(scope) == "10.0.0.9"


class TestFailureLimiter:
    def test_allows_until_threshold(self):
        limiter = _FailureLimiter(max_failures=2, window_seconds=60)
        assert limiter.is_blocked("a") is False
        limiter.record_failure("a")
        assert limiter.is_blocked("a") is False
        limiter.record_failure("a")
        assert limiter.is_blocked("a") is True

    def test_success_resets(self):
        limiter = _FailureLimiter(max_failures=1, window_seconds=60)
        limiter.record_failure("a")
        assert limiter.is_blocked("a") is True
        limiter.reset("a")
        assert limiter.is_blocked("a") is False

    def test_keys_are_independent(self):
        limiter = _FailureLimiter(max_failures=1, window_seconds=60)
        limiter.record_failure("a")
        assert limiter.is_blocked("a") is True
        assert limiter.is_blocked("b") is False

    def test_window_expiry(self, monkeypatch):
        import app.security.auth as auth

        now = {"t": 1000.0}
        monkeypatch.setattr(auth.time, "monotonic", lambda: now["t"])

        limiter = _FailureLimiter(max_failures=1, window_seconds=10)
        limiter.record_failure("a")
        assert limiter.is_blocked("a") is True
        now["t"] += 11
        assert limiter.is_blocked("a") is False

"""Tests for the hosting-oriented security gate.

Covers:
- the exposure guard that refuses a non-loopback bind without a token;
- the failed-token rate limiter used by TokenAuthMiddleware;
- the systemd unit hardening rendered by scripts/install-service.sh (issue #14).
"""
import re
import shutil
import subprocess
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


REPO_ROOT = Path(__file__).resolve().parents[2]
UNIT_TEMPLATE = REPO_ROOT / "deploy" / "odin.service"
INSTALLER = REPO_ROOT / "scripts" / "install-service.sh"

# Directives the hardened hosting unit must keep (issue #14). The rationale for
# the ones deliberately *not* set is documented in README.deploy.md.
REQUIRED_HARDENING = {
    "NoNewPrivileges": "true",
    "ProtectSystem": "strict",
    "PrivateTmp": "true",
    "PrivateDevices": "true",
    "ProtectKernelTunables": "true",
    "ProtectKernelModules": "true",
    "ProtectControlGroups": "true",
    "ProtectClock": "true",
    "ProtectHostname": "true",
    "ProtectKernelLogs": "true",
    "RestrictSUIDSGID": "true",
    "RestrictNamespaces": "true",
    "RestrictRealtime": "true",
    "LockPersonality": "true",
    "SystemCallArchitectures": "native",
    "RemoveIPC": "true",
    "UMask": "0077",
}


def _unit_directives(text: str) -> dict[str, str]:
    directives: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith(("#", "[")):
            continue
        key, sep, value = line.partition("=")
        if sep:
            directives[key] = value.strip()
    return directives


class TestServiceUnitHardening:
    def _directives(self):
        return _unit_directives(UNIT_TEMPLATE.read_text(encoding="utf-8"))

    def test_required_hardening_directives(self):
        directives = self._directives()
        for key, value in REQUIRED_HARDENING.items():
            assert directives.get(key) == value, f"{key} should be {value!r}"

    def test_capabilities_are_dropped(self):
        # Empty value = no capabilities at all (the service is unprivileged).
        assert self._directives().get("CapabilityBoundingSet") == ""

    def test_protect_home_is_rendered_by_the_installer(self):
        assert self._directives().get("ProtectHome") == "__PROTECT_HOME__"

    def test_readwrite_paths_cover_repo_and_workspace(self):
        value = self._directives()["ReadWritePaths"]
        assert "__ODIN_ROOT__" in value
        assert "__ODIN_WORKSPACE__" in value

    def test_service_drops_home_only_when_possible(self):
        # The installer must not hide /home when the checkout lives there.
        text = INSTALLER.read_text(encoding="utf-8")
        assert "read-only" in text
        assert "/home/*" in text


class TestInstallerRendersTheUnit:
    """`install-service.sh --print` must resolve every placeholder."""

    # Every placeholder the template actually uses. `__PLACEHOLDERS__` in the
    # header comment is documentation, not a substitution token.
    PLACEHOLDERS = (
        "__ODIN_ROOT__",
        "__ODIN_USER__",
        "__ODIN_WORKSPACE__",
        "__PROTECT_HOME__",
        "__EXTRA_READ_WRITE_PATHS__",
    )

    @pytest.fixture(autouse=True)
    def _require_bash(self):
        if shutil.which("bash") is None:
            pytest.skip("bash not available")

    def _fake_repo(self, tmp_path: Path, env: str) -> Path:
        root = tmp_path / "odin"
        (root / "deploy").mkdir(parents=True)
        (root / "scripts").mkdir()
        shutil.copy(UNIT_TEMPLATE, root / "deploy" / "odin.service")
        shutil.copy(INSTALLER, root / "scripts" / "install-service.sh")
        (root / ".env").write_text(env, encoding="utf-8")
        return root

    def _render(self, root: Path) -> str:
        result = subprocess.run(
            ["bash", str(root / "scripts" / "install-service.sh"), "--print"],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout

    def test_template_only_uses_known_placeholders(self):
        text = UNIT_TEMPLATE.read_text(encoding="utf-8")
        found = set(re.findall(r"__[A-Z][A-Z_]*__", text)) - {"__PLACEHOLDERS__"}
        assert found == set(self.PLACEHOLDERS)
        # …and the installer knows how to replace every one of them.
        installer = INSTALLER.read_text(encoding="utf-8")
        for placeholder in self.PLACEHOLDERS:
            assert placeholder in installer

    def test_script_is_valid_bash(self):
        assert subprocess.run(["bash", "-n", str(INSTALLER)]).returncode == 0

    def test_no_placeholder_survives(self, tmp_path):
        root = self._fake_repo(tmp_path, "ODIN_WORKSPACE=/srv/odin/workspace\n")
        rendered = self._render(root)
        for placeholder in self.PLACEHOLDERS:
            assert placeholder not in rendered
        assert "ProtectSystem=strict" in rendered

    def test_home_checkout_falls_back_to_read_only(self, tmp_path):
        root = self._fake_repo(tmp_path, "ODIN_WORKSPACE=/home/svc/odin-workspace\n")
        # The fake repo itself lives under /tmp; force a home path for the
        # workspace and assert that is enough to avoid hiding /home entirely.
        rendered = self._render(root)
        assert "ProtectHome=read-only" in rendered

    def test_absolute_database_url_gets_a_writable_dir(self, tmp_path):
        env = (
            "ODIN_WORKSPACE=/srv/odin/workspace\n"
            "DATABASE_URL=sqlite+aiosqlite:////var/lib/odin/odin.db\n"
            "ODIN_MEMORY_PATH=/var/lib/odin/memory\n"
        )
        rendered = self._render(self._fake_repo(tmp_path, env))
        rw = _unit_directives(rendered)["ReadWritePaths"]
        assert "/var/lib/odin" in rw
        # Deduplicated even though both settings share the directory.
        assert rw.count("/var/lib/odin") == 1
        assert _unit_directives(rendered)["ProtectHome"] in {"true", "read-only"}

    def test_relative_database_url_adds_no_extra_path(self, tmp_path):
        env = "ODIN_WORKSPACE=/srv/odin/workspace\nDATABASE_URL=sqlite+aiosqlite:///./odin.db\n"
        root = self._fake_repo(tmp_path, env)
        rendered = self._render(root)
        rw = _unit_directives(rendered)["ReadWritePaths"].split()
        # Exactly the repo root and the workspace, nothing else.
        assert rw == [str(root), "/srv/odin/workspace"]


"""Security tests - path guard and policy validation.

Tests the fundamental security boundaries that protect the system.
"""
import os
import sys
import pytest
from pathlib import Path
import tempfile

# Make sure we can import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

# Set a test workspace
TEST_WORKSPACE = "/tmp/odin-test-workspace"
os.environ["ODIN_WORKSPACE"] = TEST_WORKSPACE
os.environ["GEMINI_API_KEY"] = "test-key"

# Import after env is set
from app.security.path_guard import PathGuard
from app.security.policy import SecurityPolicy, OperationType, AccessLevel


@pytest.fixture
def workspace(tmp_path):
    """Create a temporary workspace for testing."""
    ws = tmp_path / "workspace"
    ws.mkdir()
    os.environ["ODIN_WORKSPACE"] = str(ws)
    return ws


@pytest.fixture
def path_guard(workspace):
    # Reload settings with new workspace
    from importlib import reload
    import app.config as cfg
    cfg.get_settings.cache_clear()
    reload(cfg)
    pg = PathGuard()
    pg.workspace = workspace.resolve()
    return pg


@pytest.fixture
def policy(path_guard):
    return SecurityPolicy(path_guard)


class TestPathGuard:
    def test_workspace_file_is_inside(self, path_guard, workspace):
        """Files inside workspace should be detected correctly."""
        test_file = workspace / "file.txt"
        assert path_guard.is_within_workspace(test_file)

    def test_workspace_subdir_is_inside(self, path_guard, workspace):
        """Subdirectories inside workspace should be detected correctly."""
        sub = workspace / "sub" / "deep" / "file.txt"
        assert path_guard.is_within_workspace(sub)

    def test_path_traversal_blocked(self, path_guard, workspace):
        """Path traversal (../) should resolve correctly and be outside workspace."""
        traversal = workspace / ".." / "outside.txt"
        # The path should resolve to outside the workspace
        resolved = path_guard.resolve_path(traversal)
        assert not path_guard.is_within_workspace(traversal)

    def test_deep_traversal_blocked(self, path_guard, workspace):
        """Deep path traversal should not escape workspace."""
        traversal = workspace / ".." / ".." / "etc" / "passwd"
        assert not path_guard.is_within_workspace(traversal)

    def test_absolute_outside_path(self, path_guard):
        """Absolute paths outside workspace should not be within workspace."""
        assert not path_guard.is_within_workspace("/etc/passwd")
        assert not path_guard.is_within_workspace("/home/caua/some-project")

    def test_etc_not_safe_to_read_virtual(self, path_guard):
        """/proc, /sys, /dev are not safe to read."""
        assert not path_guard.is_safe_to_read("/proc/1/maps")
        assert not path_guard.is_safe_to_read("/sys/kernel/security")
        assert not path_guard.is_safe_to_read("/dev/mem")

    def test_etc_is_safe_to_read(self, path_guard):
        """/etc IS safe to read (just needs approval to write)."""
        assert path_guard.is_safe_to_read("/etc/hosts")
        assert path_guard.is_safe_to_read("/etc/passwd")

    def test_symlink_escape_detection(self, path_guard, workspace):
        """Symlinks pointing outside workspace should be detected."""
        import tempfile
        # Create a symlink inside workspace pointing outside
        outside = workspace.parent / "outside_file.txt"
        outside.write_text("secret")
        link = workspace / "evil_link.txt"
        link.symlink_to(outside)

        # The symlink itself is in workspace, but resolved target is outside
        assert not path_guard.check_symlink_escape(link)

        # Cleanup
        link.unlink()
        outside.unlink()

    def test_legitimate_file_no_symlink_escape(self, path_guard, workspace):
        """Regular files inside workspace pass symlink check."""
        test_file = workspace / "real_file.txt"
        test_file.write_text("hello")
        assert path_guard.check_symlink_escape(test_file)
        test_file.unlink()


class TestSecurityPolicy:
    def test_read_inside_workspace_allowed(self, policy, workspace):
        test_file = workspace / "file.txt"
        decision = policy.check_file_operation(str(test_file), OperationType.READ)
        assert decision.level == AccessLevel.ALLOW

    def test_write_inside_workspace_allowed(self, policy, workspace):
        test_file = workspace / "output.txt"
        decision = policy.check_file_operation(str(test_file), OperationType.WRITE)
        assert decision.level == AccessLevel.ALLOW

    def test_delete_inside_workspace_allowed(self, policy, workspace):
        test_file = workspace / "delete_me.txt"
        decision = policy.check_file_operation(str(test_file), OperationType.DELETE)
        assert decision.level == AccessLevel.ALLOW

    def test_read_outside_workspace_allowed(self, policy):
        decision = policy.check_file_operation("/etc/hosts", OperationType.READ)
        assert decision.level == AccessLevel.ALLOW

    def test_write_outside_workspace_requires_approval(self, policy):
        decision = policy.check_file_operation("/etc/hosts", OperationType.WRITE)
        assert decision.level == AccessLevel.REQUIRE_APPROVAL

    def test_delete_outside_workspace_requires_approval(self, policy):
        decision = policy.check_file_operation("/home/user/file.txt", OperationType.DELETE)
        assert decision.level == AccessLevel.REQUIRE_APPROVAL

    def test_path_traversal_outside_requires_approval_for_write(self, policy, workspace):
        traversal = str(workspace) + "/../outside.txt"
        decision = policy.check_file_operation(traversal, OperationType.WRITE)
        assert decision.level == AccessLevel.REQUIRE_APPROVAL

    def test_proc_read_denied(self, policy):
        decision = policy.check_file_operation("/proc/1/mem", OperationType.READ)
        assert decision.level == AccessLevel.DENY

    def test_sys_read_denied(self, policy):
        decision = policy.check_file_operation("/sys/kernel/debug", OperationType.READ)
        assert decision.level == AccessLevel.DENY

    def test_etc_passwd_write_is_high_risk(self, policy):
        decision = policy.check_file_operation("/etc/passwd", OperationType.WRITE)
        assert decision.level == AccessLevel.REQUIRE_APPROVAL
        assert decision.risk_level.value == "high"


class TestCommandPolicy:
    def test_git_allowed(self, policy):
        decision = policy.check_command("git status")
        assert decision.level == AccessLevel.ALLOW

    def test_python_allowed(self, policy):
        decision = policy.check_command("python3 script.py")
        assert decision.level == AccessLevel.ALLOW

    def test_npm_allowed(self, policy):
        decision = policy.check_command("npm install")
        assert decision.level == AccessLevel.ALLOW  # npm is in SAFE_DEV_EXECUTABLES

    def test_sudo_requires_approval(self, policy):
        decision = policy.check_command("sudo pacman -S nodejs")
        assert decision.level == AccessLevel.REQUIRE_APPROVAL
        assert decision.risk_level.value == "critical"

    def test_pacman_requires_approval(self, policy):
        decision = policy.check_command("pacman -S nodejs")
        assert decision.level == AccessLevel.REQUIRE_APPROVAL
        assert decision.risk_level.value == "high"

    def test_systemctl_requires_approval(self, policy):
        decision = policy.check_command("systemctl start nginx")
        assert decision.level == AccessLevel.REQUIRE_APPROVAL

    def test_empty_command_denied(self, policy):
        decision = policy.check_command("")
        assert decision.level == AccessLevel.DENY

    def test_dd_requires_approval(self, policy):
        decision = policy.check_command("dd if=/dev/zero of=/dev/sda")
        assert decision.level == AccessLevel.REQUIRE_APPROVAL
        assert decision.risk_level.value == "critical"

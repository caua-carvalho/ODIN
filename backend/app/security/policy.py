from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import logging

from app.security.path_guard import PathGuard

logger = logging.getLogger("odin.security.policy")


class AccessLevel(str, Enum):
    ALLOW = "allow"
    REQUIRE_APPROVAL = "require_approval"
    DENY = "deny"


class OperationType(str, Enum):
    READ = "read"
    WRITE = "write"
    DELETE = "delete"
    MOVE = "move"
    EXECUTE = "execute"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class PolicyDecision:
    level: AccessLevel
    reason: str
    risk_level: RiskLevel = RiskLevel.LOW


# Executables that always require approval (privileged/system-altering)
PRIVILEGED_EXECUTABLES = frozenset({"sudo", "su", "doas", "pkexec"})
PACKAGE_MANAGERS = frozenset({"pacman", "apt", "apt-get", "dnf", "yum", "snap", "flatpak", "brew"})
SYSTEM_SERVICES = frozenset({"systemctl", "service", "journalctl", "crontab", "rc-service"})
HIGH_RISK_DESTRUCTIVE = frozenset({"mkfs", "fdisk", "parted", "dd", "shred", "wipefs"})

# Executables allowed without approval when working in workspace
SAFE_DEV_EXECUTABLES = frozenset({
    "git", "python", "python3", "node", "npm", "npx", "yarn", "pnpm",
    "pytest", "cargo", "go", "make", "gcc", "g++", "clang", "rustc",
    "ls", "cat", "grep", "find", "awk", "sed", "head", "tail", "wc",
    "echo", "pwd", "env", "which", "whoami", "date", "curl", "wget",
    "jq", "tree", "du", "df", "uname", "ps", "top", "htop", "free",
    "tar", "zip", "unzip", "gzip", "gunzip", "ssh", "scp", "rsync",
    "mkdir", "touch", "cp", "mv", "rm", "chmod", "chown",
})


class SecurityPolicy:
    """Central security authority. All operations must pass through this."""

    def __init__(self, path_guard: PathGuard) -> None:
        self.path_guard = path_guard

    def check_file_operation(
        self, path: str, operation: OperationType
    ) -> PolicyDecision:
        """Determine access level for a file operation."""
        resolved = self.path_guard.resolve_path(path)

        # Check for symlink escape
        if not self.path_guard.check_symlink_escape(path):
            return PolicyDecision(
                AccessLevel.DENY,
                f"Symlink escape detected: {path}",
                RiskLevel.CRITICAL,
            )

        # Inside workspace → always allowed
        if self.path_guard.is_within_workspace(path):
            logger.debug(f"ALLOW {operation} on workspace path: {resolved}")
            return PolicyDecision(
                AccessLevel.ALLOW, "Within workspace - full access granted"
            )

        # Outside workspace
        if operation == OperationType.READ:
            if self.path_guard.is_safe_to_read(path):
                logger.debug(f"ALLOW READ on system path: {resolved}")
                return PolicyDecision(
                    AccessLevel.ALLOW, "System read access granted", RiskLevel.LOW
                )
            return PolicyDecision(
                AccessLevel.DENY,
                f"Reading from {resolved} is not allowed",
                RiskLevel.HIGH,
            )

        # WRITE/DELETE/MOVE outside workspace → approval required
        risk = self._assess_path_risk(str(resolved))
        logger.info(f"REQUIRE_APPROVAL for {operation} on: {resolved} (risk: {risk})")
        return PolicyDecision(
            AccessLevel.REQUIRE_APPROVAL,
            f"{operation.value.title()} outside workspace requires authorization",
            risk,
        )

    def check_command(self, command: str) -> PolicyDecision:
        """Classify a shell command and determine required access level."""
        stripped = command.strip()
        if not stripped:
            return PolicyDecision(AccessLevel.DENY, "Empty command", RiskLevel.LOW)

        # Extract base executable
        parts = stripped.split()
        executable = Path(parts[0]).name  # handle full paths like /usr/bin/sudo

        # Critical: always deny or require approval
        if executable in PRIVILEGED_EXECUTABLES:
            return PolicyDecision(
                AccessLevel.REQUIRE_APPROVAL,
                f"Privileged command '{executable}' requires authorization",
                RiskLevel.CRITICAL,
            )

        if executable in HIGH_RISK_DESTRUCTIVE:
            return PolicyDecision(
                AccessLevel.REQUIRE_APPROVAL,
                f"Destructive command '{executable}' requires authorization",
                RiskLevel.CRITICAL,
            )

        if executable in PACKAGE_MANAGERS:
            return PolicyDecision(
                AccessLevel.REQUIRE_APPROVAL,
                f"Package manager '{executable}' requires authorization",
                RiskLevel.HIGH,
            )

        if executable in SYSTEM_SERVICES:
            return PolicyDecision(
                AccessLevel.REQUIRE_APPROVAL,
                f"System service command '{executable}' requires authorization",
                RiskLevel.HIGH,
            )

        # Allow common dev tools
        if executable in SAFE_DEV_EXECUTABLES:
            return PolicyDecision(
                AccessLevel.ALLOW, f"Development command '{executable}' allowed"
            )

        # Unknown commands: require approval for safety
        logger.info(f"Unknown command '{executable}' - requiring approval")
        return PolicyDecision(
            AccessLevel.REQUIRE_APPROVAL,
            f"Unknown command '{executable}' requires authorization",
            RiskLevel.MEDIUM,
        )

    def requires_approval(self, decision: PolicyDecision) -> bool:
        return decision.level == AccessLevel.REQUIRE_APPROVAL

    def is_denied(self, decision: PolicyDecision) -> bool:
        return decision.level == AccessLevel.DENY

    def _assess_path_risk(self, path: str) -> RiskLevel:
        """Estimate risk level for writing to a system path."""
        high_risk_prefixes = ["/etc", "/usr", "/bin", "/sbin", "/boot", "/root"]
        for prefix in high_risk_prefixes:
            if path.startswith(prefix):
                return RiskLevel.HIGH
        return RiskLevel.MEDIUM

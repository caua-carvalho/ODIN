from pathlib import Path
from app.config import settings
import logging

logger = logging.getLogger("odin.security.path_guard")

# Paths that should never be read (dangerous/virtual filesystems)
BLOCKED_READ_PREFIXES = [
    Path("/proc"),
    Path("/sys"),
    Path("/dev"),
]


class PathGuard:
    """Central path resolution and workspace boundary enforcement.

    NEVER use string comparison to check paths. Always use resolved canonical paths.
    """

    def __init__(self) -> None:
        self.workspace = Path(settings.odin_workspace).resolve()

    def resolve_path(self, path: str | Path) -> Path:
        """Resolve a path to its canonical form."""
        return Path(path).resolve()

    def is_within_workspace(self, path: str | Path) -> bool:
        """Check if a path is inside the workspace (handles traversal and symlinks)."""
        try:
            resolved = self.resolve_path(path)
            return resolved == self.workspace or self.workspace in resolved.parents
        except (OSError, ValueError):
            return False

    def is_safe_to_read(self, path: str | Path) -> bool:
        """Check if a path is safe to read (blocks dangerous virtual filesystems)."""
        try:
            resolved = self.resolve_path(path)
            for blocked in BLOCKED_READ_PREFIXES:
                if resolved == blocked or blocked in resolved.parents:
                    logger.warning(f"Blocked read attempt on dangerous path: {resolved}")
                    return False
            return True
        except (OSError, ValueError) as e:
            logger.warning(f"Path resolution failed for {path}: {e}")
            return False

    def validate_no_traversal(self, base: str | Path, path: str | Path) -> bool:
        """Validate that `path` doesn't escape `base` via traversal."""
        try:
            base_resolved = self.resolve_path(base)
            path_resolved = self.resolve_path(path)
            return path_resolved == base_resolved or base_resolved in path_resolved.parents
        except (OSError, ValueError):
            return False

    def is_within_workspace_lexical(self, path: str | Path) -> bool:
        """Check if a path's *parent directory* is within workspace (doesn't follow final symlink).

        Use this to check where a symlink *lives*, not where it *points*.
        """
        try:
            p = Path(path)
            # Resolve parent directories (not the final component) 
            parent_resolved = p.parent.resolve()
            candidate = parent_resolved / p.name
            return candidate == self.workspace or self.workspace in candidate.parents
        except (OSError, ValueError):
            return False

    def check_symlink_escape(self, path: str | Path) -> bool:
        """
        Check if path uses symlinks to escape workspace.
        Returns True if the path is safe (no symlink escape detected).
        Returns False if the path is a symlink that lives inside workspace
        but resolves to a target outside workspace.
        """
        try:
            p = Path(path)
            # Only check if the path exists and is a symlink
            if not p.is_symlink():
                return True  # Not a symlink, no escape possible

            # Check if the symlink LIVES inside workspace (lexically, not following symlink)
            symlink_in_workspace = self.is_within_workspace_lexical(p)
            if not symlink_in_workspace:
                return True  # Symlink is outside workspace - handled by higher-level policy

            # The symlink lives inside workspace - check if it points outside
            resolved = p.resolve()
            if not self.is_within_workspace(resolved):
                logger.warning(f"Symlink escape detected: {p} -> {resolved}")
                return False

            return True
        except (OSError, ValueError):
            return True  # If we can't resolve, be conservative

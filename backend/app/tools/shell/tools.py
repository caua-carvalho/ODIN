import asyncio
import json
import logging
import os
import signal
import uuid
from datetime import datetime, UTC

from app.security.path_guard import PathGuard
from app.security.policy import SecurityPolicy
from app.security.permissions import permission_manager
from app.tools.base import ToolDefinition, ToolResult

logger = logging.getLogger("odin.tools.shell")

# Timeout policy for ``execute_command`` (issue #19):
#   * default: COMMAND_TIMEOUT
#   * per-call override: the ``timeout`` argument
#   * hard cap: MAX_COMMAND_TIMEOUT — overrides are clamped to it
# On timeout *and* on turn cancellation the whole process group is terminated
# with SIGTERM, then SIGKILL after TERMINATE_GRACE_SECONDS if anything survives.
COMMAND_TIMEOUT = 60  # seconds
MAX_COMMAND_TIMEOUT = 300  # seconds
TERMINATE_GRACE_SECONDS = 2.0  # SIGTERM -> SIGKILL grace for the process group


class ExecuteCommandTool:
    """Execute shell commands with security classification."""

    def __init__(
        self,
        security: SecurityPolicy,
        path_guard: PathGuard,
        ws_manager=None,
    ) -> None:
        self.security = security
        self.path_guard = path_guard
        self.ws_manager = ws_manager

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="execute_command",
            description=(
                "Execute a shell command. Safe development commands (git, python, npm, etc.) "
                "within the workspace run automatically. Privileged or system-altering commands "
                "require user authorization."
            ),
            category="shell",
            parameters_schema={
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The shell command to execute.",
                    },
                    "working_directory": {
                        "type": "string",
                        "description": "Working directory for the command. Defaults to workspace.",
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "Timeout in seconds (max 300).",
                        "default": 60,
                    },
                },
                "required": ["command"],
            },
        )

    async def execute(self, arguments: dict, conversation_id: str) -> ToolResult:
        command: str = arguments.get("command", "").strip()
        working_dir: str = arguments.get(
            "working_directory", str(self.path_guard.workspace)
        )
        timeout: int = min(
            arguments.get("timeout", COMMAND_TIMEOUT), MAX_COMMAND_TIMEOUT
        )

        if not command:
            return ToolResult(success=False, error="Empty command")

        decision = self.security.check_command(command)

        if self.security.is_denied(decision):
            return ToolResult(success=False, error=f"Command denied: {decision.reason}")

        if self.security.requires_approval(decision):
            approved, req_id = await self._request_permission(
                conversation_id=conversation_id,
                command=command,
                reason=decision.reason,
                risk_level=decision.risk_level.value,
            )
            if not approved:
                return ToolResult(
                    success=False,
                    error="Command execution denied by user.",
                    permission_request_id=req_id,
                )

        # Validate working directory
        try:
            wd_path = self.path_guard.resolve_path(working_dir)
            if not wd_path.is_dir():
                wd_path = self.path_guard.workspace
        except Exception:
            wd_path = self.path_guard.workspace

        logger.info(f"execute_command: {command!r} cwd={wd_path}")

        proc = None
        termination_reason: str | None = None
        process_completed = False
        try:
            # ``start_new_session=True`` puts the shell in its own session and
            # process group, so killing the group below reaches every descendant
            # (``bash -c 'sleep 300 &'``) instead of only the shell itself.
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd=str(wd_path),
                env={**os.environ},
                start_new_session=True,
            )

            try:
                stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            except asyncio.TimeoutError:
                termination_reason = "timeout"
                return ToolResult(
                    success=False,
                    error=f"Command timed out after {timeout}s: {command}",
                )
            except asyncio.CancelledError:
                # A user "stop" cancels the whole turn; unlike ``Exception``,
                # ``CancelledError`` is a ``BaseException`` so it must be caught
                # explicitly. Kill the tree, then let the cancellation propagate
                # so the WebSocket can still answer ``{"type":"done","cancelled":true}``.
                termination_reason = "cancelled"
                raise

            process_completed = True
            output = stdout.decode("utf-8", errors="replace") if stdout else ""
            success = proc.returncode == 0

            logger.info(f"execute_command completed: exit_code={proc.returncode}")
            return ToolResult(
                success=success,
                output={
                    "stdout": output,
                    "exit_code": proc.returncode,
                    "command": command,
                    "working_directory": str(wd_path),
                },
                error=None if success else f"Command exited with code {proc.returncode}",
            )
        except asyncio.CancelledError:
            termination_reason = termination_reason or "cancelled"
            raise
        except FileNotFoundError:
            return ToolResult(success=False, error=f"Command not found: {command.split()[0]}")
        except Exception as e:
            return ToolResult(success=False, error=str(e))
        finally:
            # Single cleanup path: runs on success, timeout, cancellation and
            # unexpected errors alike. The process was not reaped on the normal
            # path, so its process group may still hold descendants even if the
            # direct shell child already exited (e.g. ``bash -c 'sleep 300 &'``
            # keeps the stdout pipe open). Killing the group is therefore gated
            # on ``process_completed``, not on ``proc.returncode``.
            if proc is not None and not process_completed:
                await self._terminate_process_group(
                    proc, command, reason=termination_reason or "cleanup"
                )

    async def _terminate_process_group(
        self, proc: asyncio.subprocess.Process, command: str, reason: str
    ) -> None:
        """Terminate the shell and every descendant it spawned.

        ``start_new_session=True`` made the shell a session/group leader, so its
        pid *is* the process-group id: ``os.killpg(proc.pid, ...)`` reaches the
        whole tree even after the leader itself has been reaped. The group is
        asked to stop with ``SIGTERM``, given a short grace period, then
        ``SIGKILL``-ed if a member survives. Safe on an already-dead group.
        """
        pgid = proc.pid

        try:
            os.killpg(pgid, signal.SIGTERM)
            logger.warning(
                "execute_command %s: SIGTERM -> process group %s (%r)",
                reason,
                pgid,
                command,
            )
        except ProcessLookupError:
            logger.warning(
                "execute_command %s: process group %s already gone (%r)",
                reason,
                pgid,
                command,
            )
        except OSError:  # pragma: no cover - defensive
            pass

        try:
            waited = 0.0
            while waited < TERMINATE_GRACE_SECONDS and self._group_alive(pgid):
                await asyncio.sleep(0.05)
                waited += 0.05

            if self._group_alive(pgid):
                os.killpg(pgid, signal.SIGKILL)
                logger.warning(
                    "execute_command %s: SIGKILL -> process group %s (%r)",
                    reason,
                    pgid,
                    command,
                )
        except asyncio.CancelledError:
            # The cleanup itself was cancelled (a second stop): escalate to
            # SIGKILL and re-raise so the cancellation still propagates.
            try:
                os.killpg(pgid, signal.SIGKILL)
            except OSError:
                pass
            raise
        except OSError:  # pragma: no cover - defensive
            pass
        finally:
            await self._reap(proc)

    @staticmethod
    def _group_alive(pgid: int) -> bool:
        """Whether any process still belongs to ``pgid`` (``kill 0`` probe)."""
        try:
            os.killpg(pgid, 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:  # pragma: no cover - we own the group
            return True

    @staticmethod
    async def _reap(proc: asyncio.subprocess.Process) -> None:
        """Drain pipes and reap the direct child so no zombie/pipe fd leaks."""
        try:
            await proc.communicate()
        except Exception:  # pragma: no cover - best effort
            pass
        try:
            await proc.wait()
        except Exception:  # pragma: no cover - best effort
            pass

    async def _request_permission(
        self,
        conversation_id: str,
        command: str,
        reason: str,
        risk_level: str,
    ) -> tuple[bool, str]:
        from app.database.session import get_db_session
        from app.database.models import PermissionRequest

        request_id = str(uuid.uuid4())

        async with get_db_session() as db:
            perm_req = PermissionRequest(
                id=request_id,
                conversation_id=conversation_id,
                tool="execute_command",
                operation="EXECUTE",
                arguments_json=json.dumps({"command": command}),
                target=command,
                reason=reason,
                risk_level=risk_level,
                status="pending",
                created_at=datetime.now(UTC),
            )
            db.add(perm_req)

        if self.ws_manager:
            await self.ws_manager.broadcast_to_conversation(
                conversation_id,
                {
                    "type": "permission_request",
                    "id": request_id,
                    "tool": "execute_command",
                    "operation": "EXECUTE",
                    "target": command,
                    "reason": reason,
                    "risk_level": risk_level,
                    "arguments": {"command": command},
                },
            )

        approved = await permission_manager.request_approval(request_id)

        async with get_db_session() as db:
            from sqlalchemy import select
            result = await db.execute(
                select(PermissionRequest).where(PermissionRequest.id == request_id)
            )
            perm = result.scalar_one_or_none()
            if perm:
                perm.status = "approved" if approved else "denied"
                perm.resolved_at = datetime.now(UTC)

        return approved, request_id

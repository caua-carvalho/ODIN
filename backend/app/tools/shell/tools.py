import asyncio
import json
import logging
import os
import uuid
from datetime import datetime, UTC
from pathlib import Path

from app.security.path_guard import PathGuard
from app.security.policy import SecurityPolicy, OperationType
from app.security.permissions import permission_manager
from app.tools.base import BaseTool, ToolDefinition, ToolResult

logger = logging.getLogger("odin.tools.shell")

COMMAND_TIMEOUT = 60  # seconds


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
        timeout: int = min(arguments.get("timeout", COMMAND_TIMEOUT), 300)

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

        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd=str(wd_path),
                env={**os.environ},
            )

            try:
                stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.communicate()
                return ToolResult(
                    success=False,
                    error=f"Command timed out after {timeout}s: {command}",
                )

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

        except FileNotFoundError:
            return ToolResult(success=False, error=f"Command not found: {command.split()[0]}")
        except Exception as e:
            return ToolResult(success=False, error=str(e))

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

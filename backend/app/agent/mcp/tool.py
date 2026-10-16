"""Adapt external MCP tools to Odin's ``BaseTool`` contract.

Every tool discovered on an MCP server is wrapped in an ``McpToolAdapter`` and
registered in the ``ToolRegistry`` exactly like a native tool. The important
part is the security gate: MCP tools execute inside a **separate process** that
``PathGuard`` cannot inspect, so by default each call requires explicit user
approval (the same HITL flow ``execute_command`` uses). Only servers explicitly
marked ``trusted`` in ``ODIN_MCP_SERVERS`` skip that blanket approval — and even
then, any declared path argument is still checked against the workspace
boundary by the shared ``SecurityPolicy``.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime, UTC
from typing import Any, Iterator

from app.security.permissions import permission_manager
from app.security.policy import (
    AccessLevel,
    OperationType,
    PolicyDecision,
    RiskLevel,
    SecurityPolicy,
)
from app.tools.base import ToolDefinition, ToolResult

logger = logging.getLogger("odin.agent.mcp.tool")

# Argument keys that conventionally carry a filesystem path. Used for trusted
# servers only, to keep their (still external) file access inside the workspace
# boundary. False positives are harmless: a non-path string simply resolves
# somewhere inside the workspace and is allowed.
_PATH_ARGUMENT_KEYS = frozenset(
    {
        "path",
        "paths",
        "file",
        "files",
        "file_path",
        "filepath",
        "filename",
        "directory",
        "dir",
        "source",
        "destination",
        "src",
        "dst",
        "working_directory",
        "cwd",
    }
)

_LEVEL_ORDER = {
    AccessLevel.ALLOW: 0,
    AccessLevel.REQUIRE_APPROVAL: 1,
    AccessLevel.DENY: 2,
}
_RISK_ORDER = {
    RiskLevel.LOW: 0,
    RiskLevel.MEDIUM: 1,
    RiskLevel.HIGH: 2,
    RiskLevel.CRITICAL: 3,
}


def _sanitize(name: str) -> str:
    """Make a server/tool name safe inside an LLM function name."""
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "_", name or "").strip("_")
    return cleaned or "tool"


def _most_restrictive(a: PolicyDecision, b: PolicyDecision) -> PolicyDecision:
    if _LEVEL_ORDER[b.level] > _LEVEL_ORDER[a.level]:
        return b
    if _LEVEL_ORDER[b.level] == _LEVEL_ORDER[a.level]:
        if _RISK_ORDER[b.risk_level] > _RISK_ORDER[a.risk_level]:
            return b
    return a


class McpToolInfo:
    """Normalized description of a tool advertised by an MCP server."""

    def __init__(
        self,
        server: str,
        trusted: bool,
        name: str,
        description: str,
        input_schema: dict,
        read_only: bool,
    ) -> None:
        self.server = server
        self.trusted = trusted
        self.name = name
        self.description = description
        self.input_schema = input_schema
        self.read_only = read_only
        # Namespaced so MCP tools can never collide with Odin's native tools.
        self.qualified_name = f"mcp__{_sanitize(server)}__{_sanitize(name)}"

    @classmethod
    def from_tool(cls, server: str, trusted: bool, tool: Any) -> "McpToolInfo":
        annotations = getattr(tool, "annotations", None)
        read_only = bool(getattr(annotations, "read_only_hint", False)) if annotations else False
        # Field name changed between SDK majors; accept both.
        schema = (
            getattr(tool, "input_schema", None)
            or getattr(tool, "inputSchema", None)
            or {"type": "object", "properties": {}}
        )
        return cls(
            server=server,
            trusted=trusted,
            name=getattr(tool, "name", "") or "",
            description=getattr(tool, "description", "") or "",
            input_schema=schema,
            read_only=read_only,
        )


class McpToolAdapter:
    """A ``BaseTool`` that forwards a call to an MCP server, through the gate."""

    def __init__(
        self,
        manager: Any,
        info: McpToolInfo,
        security_policy: SecurityPolicy,
        ws_manager: Any = None,
    ) -> None:
        self.manager = manager
        self.info = info
        self.security = security_policy
        self.ws_manager = ws_manager

    @property
    def definition(self) -> ToolDefinition:
        trust = "trusted server" if self.info.trusted else "requires user approval"
        description = self.info.description or f"MCP tool '{self.info.name}'"
        return ToolDefinition(
            name=self.info.qualified_name,
            description=(
                f"[MCP:{self.info.server}] {description} "
                f"(runs in an external MCP server; {trust})"
            ),
            category="mcp",
            parameters_schema=self.info.input_schema
            or {"type": "object", "properties": {}},
            requires_approval_by_default=not self.info.trusted,
        )

    async def execute(self, arguments: dict, conversation_id: str) -> ToolResult:
        arguments = arguments or {}
        intent = OperationType.READ if self.info.read_only else OperationType.EXECUTE
        decision = self._gate(arguments, intent)

        if self.security.is_denied(decision):
            logger.info(
                "MCP tool %s denied by policy: %s",
                self.info.qualified_name,
                decision.reason,
            )
            return ToolResult(success=False, error=f"Access denied: {decision.reason}")

        if self.security.requires_approval(decision):
            approved, request_id = await self._request_permission(
                conversation_id=conversation_id,
                intent=intent,
                arguments=arguments,
                decision=decision,
            )
            if not approved:
                return ToolResult(
                    success=False,
                    error="Operation denied by user.",
                    requires_approval=True,
                    permission_request_id=request_id,
                )

        logger.info(
            "MCP tool call: %s(%s)",
            self.info.qualified_name,
            json.dumps(arguments)[:200],
        )
        try:
            result = await self.manager.call_tool(
                self.info.server, self.info.name, arguments
            )
        except Exception as exc:  # server gone / transport error
            logger.warning("MCP tool %s failed: %s", self.info.qualified_name, exc)
            return ToolResult(success=False, error=f"MCP call failed: {exc}")

        return _result_to_tool_result(result)

    # ------------------------------------------------------------------
    # Security gate
    # ------------------------------------------------------------------
    def _gate(self, arguments: dict, intent: OperationType) -> PolicyDecision:
        if not self.info.trusted:
            # The external process is opaque to PathGuard, so an untrusted
            # tool always needs explicit authorization.
            base = PolicyDecision(
                AccessLevel.REQUIRE_APPROVAL,
                (
                    f"MCP tool '{self.info.qualified_name}' runs in an external "
                    "process outside the Odin workspace boundary"
                ),
                RiskLevel.HIGH if intent == OperationType.EXECUTE else RiskLevel.MEDIUM,
            )
        else:
            base = PolicyDecision(
                AccessLevel.ALLOW, "Trusted MCP server", RiskLevel.LOW
            )

        # Even trusted servers stay inside the workspace boundary for path-like
        # arguments, using the very same policy native tools consult.
        check_op = (
            OperationType.READ if intent == OperationType.READ else OperationType.WRITE
        )
        for path in _iter_path_arguments(arguments):
            try:
                path_decision = self.security.check_file_operation(path, check_op)
            except Exception as exc:  # unparseable path -> be conservative
                logger.debug("Could not classify MCP path argument %r: %s", path, exc)
                continue
            base = _most_restrictive(base, path_decision)
        return base

    async def _request_permission(
        self,
        conversation_id: str,
        intent: OperationType,
        arguments: dict,
        decision: PolicyDecision,
    ) -> tuple[bool, str]:
        """Create a permission request and block until the user decides.

        Mirrors ``ExecuteCommandTool._request_permission`` — same DB row, same
        WebSocket event, same ``permission_manager`` — so the existing
        Approve/Deny UI works unchanged.
        """
        from app.database.models import PermissionRequest
        from app.database.session import get_db_session

        request_id = str(uuid.uuid4())
        target = f"{self.info.server}:{self.info.name}"

        async with get_db_session() as db:
            db.add(
                PermissionRequest(
                    id=request_id,
                    conversation_id=conversation_id,
                    tool=self.info.qualified_name,
                    operation=intent.value.upper(),
                    arguments_json=json.dumps(arguments),
                    target=target,
                    reason=decision.reason,
                    risk_level=decision.risk_level.value,
                    status="pending",
                    created_at=datetime.now(UTC),
                )
            )

        if self.ws_manager:
            await self.ws_manager.broadcast_to_conversation(
                conversation_id,
                {
                    "type": "permission_request",
                    "id": request_id,
                    "tool": self.info.qualified_name,
                    "operation": intent.value.upper(),
                    "target": target,
                    "reason": decision.reason,
                    "risk_level": decision.risk_level.value,
                    "arguments": arguments,
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


def _iter_path_arguments(arguments: dict) -> Iterator[str]:
    for key, value in (arguments or {}).items():
        if key not in _PATH_ARGUMENT_KEYS:
            continue
        if isinstance(value, str):
            yield value
        elif isinstance(value, (list, tuple)):
            for item in value:
                if isinstance(item, str):
                    yield item


def _result_to_tool_result(result: Any) -> ToolResult:
    """Translate an MCP ``CallToolResult`` into an Odin ``ToolResult``."""
    is_error = bool(getattr(result, "is_error", False))
    structured = getattr(result, "structured_content", None)

    texts: list[str] = []
    extra: list[dict] = []
    for block in getattr(result, "content", None) or []:
        block_type = getattr(block, "type", None)
        text = getattr(block, "text", None)
        if block_type == "text" or (text is not None and block_type is None):
            texts.append(text or "")
        elif block_type == "image" or hasattr(block, "data"):
            data = getattr(block, "data", "") or ""
            extra.append(
                {
                    "type": "image",
                    "mime_type": getattr(block, "mime_type", None),
                    "data_length": len(data),
                }
            )
        else:
            try:
                extra.append(block.model_dump())
            except Exception:
                extra.append({"type": block_type or "unknown"})

    text = "\n".join(t for t in texts if t)

    if structured is not None and text:
        output: Any = {"structured": structured, "text": text}
    elif structured is not None:
        output = structured
    elif text and extra:
        output = {"text": text, "content": extra}
    elif text:
        output = text
    elif extra:
        output = {"content": extra}
    else:
        output = ""

    error = text if (is_error and text) else ("MCP tool reported an error" if is_error else None)
    return ToolResult(success=not is_error, output=output, error=error)


def create_mcp_tools(
    manager: Any,
    security_policy: SecurityPolicy,
    ws_manager: Any = None,
) -> list[McpToolAdapter]:
    """Build one adapter per tool discovered on a connected MCP server."""
    return [
        McpToolAdapter(manager, info, security_policy, ws_manager)
        for info in manager.iter_tool_infos()
    ]

import json
import logging
import os
import uuid
from datetime import datetime, UTC
from pathlib import Path
from typing import Any

from app.security.path_guard import PathGuard
from app.security.policy import SecurityPolicy, OperationType
from app.security.permissions import permission_manager
from app.tools.base import BaseTool, ToolDefinition, ToolResult

logger = logging.getLogger("odin.tools.filesystem")


class FilesystemToolBase:
    """Shared base for all filesystem tools."""

    def __init__(
        self,
        security_policy: SecurityPolicy,
        path_guard: PathGuard,
        websocket_manager=None,
    ) -> None:
        self.security = security_policy
        self.path_guard = path_guard
        self.ws_manager = websocket_manager

    async def _request_permission(
        self,
        conversation_id: str,
        tool_name: str,
        operation: str,
        target: str,
        arguments: dict,
        reason: str,
        risk_level: str,
    ) -> tuple[bool, str]:
        """Create a permission request and wait for user approval."""
        from app.database.session import get_db_session
        from app.database.models import PermissionRequest

        request_id = str(uuid.uuid4())

        async with get_db_session() as db:
            perm_req = PermissionRequest(
                id=request_id,
                conversation_id=conversation_id,
                tool=tool_name,
                operation=operation,
                arguments_json=json.dumps(arguments),
                target=target,
                reason=reason,
                risk_level=risk_level,
                status="pending",
                created_at=datetime.now(UTC),
            )
            db.add(perm_req)

        # Notify via WebSocket if available
        if self.ws_manager:
            await self.ws_manager.broadcast_to_conversation(
                conversation_id,
                {
                    "type": "permission_request",
                    "id": request_id,
                    "tool": tool_name,
                    "operation": operation,
                    "target": target,
                    "reason": reason,
                    "risk_level": risk_level,
                    "arguments": arguments,
                },
            )

        approved = await permission_manager.request_approval(request_id)

        # Update DB with result
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


class ReadFileTool(FilesystemToolBase):
    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="read_file",
            description="Read the content of a file from the filesystem.",
            category="filesystem",
            parameters_schema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Absolute or relative path to the file to read.",
                    },
                    "encoding": {
                        "type": "string",
                        "description": "File encoding (default: utf-8)",
                        "default": "utf-8",
                    },
                },
                "required": ["path"],
            },
        )

    async def execute(self, arguments: dict, conversation_id: str) -> ToolResult:
        path = arguments.get("path", "")
        encoding = arguments.get("encoding", "utf-8")

        decision = self.security.check_file_operation(path, OperationType.READ)

        if self.security.is_denied(decision):
            return ToolResult(success=False, error=f"Access denied: {decision.reason}")

        try:
            resolved = self.path_guard.resolve_path(path)
            if not resolved.exists():
                return ToolResult(success=False, error=f"File not found: {path}")
            if not resolved.is_file():
                return ToolResult(success=False, error=f"Path is not a file: {path}")

            content = resolved.read_text(encoding=encoding, errors="replace")
            logger.info(f"read_file: {resolved}")
            return ToolResult(success=True, output=content)
        except PermissionError:
            return ToolResult(success=False, error=f"Permission denied reading: {path}")
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class ListDirectoryTool(FilesystemToolBase):
    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="list_directory",
            description="List the contents of a directory.",
            category="filesystem",
            parameters_schema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the directory to list.",
                    },
                    "show_hidden": {
                        "type": "boolean",
                        "description": "Include hidden files (starting with .)",
                        "default": False,
                    },
                },
                "required": ["path"],
            },
        )

    async def execute(self, arguments: dict, conversation_id: str) -> ToolResult:
        path = arguments.get("path", "")
        show_hidden = arguments.get("show_hidden", False)

        decision = self.security.check_file_operation(path, OperationType.READ)
        if self.security.is_denied(decision):
            return ToolResult(success=False, error=f"Access denied: {decision.reason}")

        try:
            resolved = self.path_guard.resolve_path(path)
            if not resolved.exists():
                return ToolResult(success=False, error=f"Directory not found: {path}")
            if not resolved.is_dir():
                return ToolResult(success=False, error=f"Path is not a directory: {path}")

            entries = []
            for entry in sorted(resolved.iterdir()):
                if not show_hidden and entry.name.startswith("."):
                    continue
                try:
                    stat = entry.stat()
                    entries.append(
                        {
                            "name": entry.name,
                            "type": "directory" if entry.is_dir() else "file",
                            "size": stat.st_size if entry.is_file() else None,
                            "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                        }
                    )
                except (OSError, PermissionError):
                    entries.append({"name": entry.name, "type": "unknown", "size": None, "modified": None})

            logger.info(f"list_directory: {resolved} ({len(entries)} entries)")
            return ToolResult(success=True, output={"path": str(resolved), "entries": entries})
        except PermissionError:
            return ToolResult(success=False, error=f"Permission denied: {path}")
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class SearchFilesTool(FilesystemToolBase):
    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="search_files",
            description="Search for files or text content within a directory.",
            category="filesystem",
            parameters_schema={
                "type": "object",
                "properties": {
                    "directory": {
                        "type": "string",
                        "description": "Directory to search in.",
                    },
                    "pattern": {
                        "type": "string",
                        "description": "File name glob pattern (e.g. '*.py') OR text to search in file contents.",
                    },
                    "search_content": {
                        "type": "boolean",
                        "description": "If true, search file contents for pattern. If false, search file names.",
                        "default": False,
                    },
                    "recursive": {
                        "type": "boolean",
                        "description": "Search recursively in subdirectories.",
                        "default": True,
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum number of results to return.",
                        "default": 50,
                    },
                },
                "required": ["directory", "pattern"],
            },
        )

    async def execute(self, arguments: dict, conversation_id: str) -> ToolResult:
        directory = arguments.get("directory", "")
        pattern = arguments.get("pattern", "")
        search_content = arguments.get("search_content", False)
        recursive = arguments.get("recursive", True)
        max_results = min(arguments.get("max_results", 50), 200)

        decision = self.security.check_file_operation(directory, OperationType.READ)
        if self.security.is_denied(decision):
            return ToolResult(success=False, error=f"Access denied: {decision.reason}")

        try:
            resolved = self.path_guard.resolve_path(directory)
            if not resolved.is_dir():
                return ToolResult(success=False, error=f"Not a directory: {directory}")

            results = []
            glob_fn = resolved.rglob if recursive else resolved.glob

            if search_content:
                # Search file contents
                for filepath in glob_fn("*"):
                    if len(results) >= max_results:
                        break
                    if filepath.is_file():
                        try:
                            content = filepath.read_text(errors="ignore")
                            lines_with_match = [
                                {"line": i + 1, "text": line.strip()}
                                for i, line in enumerate(content.splitlines())
                                if pattern.lower() in line.lower()
                            ]
                            if lines_with_match:
                                results.append(
                                    {
                                        "file": str(filepath.relative_to(resolved)),
                                        "matches": lines_with_match[:10],
                                    }
                                )
                        except (OSError, UnicodeDecodeError):
                            pass
            else:
                # Search file names
                for filepath in glob_fn(pattern):
                    if len(results) >= max_results:
                        break
                    results.append(
                        {
                            "path": str(filepath),
                            "type": "directory" if filepath.is_dir() else "file",
                            "relative": str(filepath.relative_to(resolved)),
                        }
                    )

            logger.info(f"search_files: {resolved} pattern='{pattern}' found={len(results)}")
            return ToolResult(
                success=True,
                output={
                    "directory": str(resolved),
                    "pattern": pattern,
                    "results": results,
                    "total": len(results),
                },
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class WriteFileTool(FilesystemToolBase):
    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="write_file",
            description="Write content to a file. Requires authorization outside workspace.",
            category="filesystem",
            requires_approval_by_default=True,
            parameters_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path to the file to write."},
                    "content": {"type": "string", "description": "Content to write."},
                    "mode": {
                        "type": "string",
                        "description": "Write mode: 'write' (overwrite) or 'append'",
                        "default": "write",
                        "enum": ["write", "append"],
                    },
                },
                "required": ["path", "content"],
            },
        )

    async def execute(self, arguments: dict, conversation_id: str) -> ToolResult:
        path = arguments.get("path", "")
        content = arguments.get("content", "")
        mode = arguments.get("mode", "write")

        decision = self.security.check_file_operation(path, OperationType.WRITE)

        if self.security.is_denied(decision):
            return ToolResult(success=False, error=f"Access denied: {decision.reason}")

        if self.security.requires_approval(decision):
            approved, req_id = await self._request_permission(
                conversation_id=conversation_id,
                tool_name="write_file",
                operation="WRITE",
                target=path,
                arguments={"path": path, "mode": mode, "content_length": len(content)},
                reason=f"Write to file outside workspace: {path}",
                risk_level=decision.risk_level.value,
            )
            if not approved:
                return ToolResult(
                    success=False,
                    error="Operation denied by user.",
                    permission_request_id=req_id,
                )

        try:
            resolved = self.path_guard.resolve_path(path)
            resolved.parent.mkdir(parents=True, exist_ok=True)
            write_mode = "a" if mode == "append" else "w"
            resolved.write_text(content) if write_mode == "w" else open(resolved, "a").write(content)
            logger.info(f"write_file: {resolved} ({len(content)} bytes)")
            return ToolResult(success=True, output={"path": str(resolved), "bytes_written": len(content)})
        except PermissionError:
            return ToolResult(success=False, error=f"Permission denied writing: {path}")
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class DeleteFileTool(FilesystemToolBase):
    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="delete_file",
            description="Delete a file or empty directory. Requires authorization outside workspace.",
            category="filesystem",
            requires_approval_by_default=True,
            parameters_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path to delete."},
                },
                "required": ["path"],
            },
        )

    async def execute(self, arguments: dict, conversation_id: str) -> ToolResult:
        path = arguments.get("path", "")

        decision = self.security.check_file_operation(path, OperationType.DELETE)

        if self.security.is_denied(decision):
            return ToolResult(success=False, error=f"Access denied: {decision.reason}")

        if self.security.requires_approval(decision):
            approved, req_id = await self._request_permission(
                conversation_id=conversation_id,
                tool_name="delete_file",
                operation="DELETE",
                target=path,
                arguments=arguments,
                reason=f"Delete file outside workspace: {path}",
                risk_level=decision.risk_level.value,
            )
            if not approved:
                return ToolResult(success=False, error="Operation denied by user.", permission_request_id=req_id)

        try:
            resolved = self.path_guard.resolve_path(path)
            if not resolved.exists():
                return ToolResult(success=False, error=f"Path not found: {path}")
            if resolved.is_dir():
                resolved.rmdir()  # Only empty dirs
            else:
                resolved.unlink()
            logger.info(f"delete_file: {resolved}")
            return ToolResult(success=True, output={"deleted": str(resolved)})
        except OSError as e:
            return ToolResult(success=False, error=str(e))


class MoveFileTool(FilesystemToolBase):
    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="move_file",
            description="Move or rename a file. Requires authorization if outside workspace.",
            category="filesystem",
            requires_approval_by_default=True,
            parameters_schema={
                "type": "object",
                "properties": {
                    "source": {"type": "string", "description": "Source path."},
                    "destination": {"type": "string", "description": "Destination path."},
                },
                "required": ["source", "destination"],
            },
        )

    async def execute(self, arguments: dict, conversation_id: str) -> ToolResult:
        source = arguments.get("source", "")
        destination = arguments.get("destination", "")

        src_decision = self.security.check_file_operation(source, OperationType.MOVE)
        dst_decision = self.security.check_file_operation(destination, OperationType.WRITE)

        needs_approval = self.security.requires_approval(src_decision) or self.security.requires_approval(dst_decision)

        if self.security.is_denied(src_decision) or self.security.is_denied(dst_decision):
            return ToolResult(success=False, error="Access denied for move operation.")

        if needs_approval:
            risk = max(src_decision.risk_level, dst_decision.risk_level, key=lambda r: ["low", "medium", "high", "critical"].index(r.value))
            approved, req_id = await self._request_permission(
                conversation_id=conversation_id,
                tool_name="move_file",
                operation="MOVE",
                target=f"{source} → {destination}",
                arguments=arguments,
                reason=f"Move file outside workspace boundary",
                risk_level=risk.value,
            )
            if not approved:
                return ToolResult(success=False, error="Operation denied by user.", permission_request_id=req_id)

        try:
            src_resolved = self.path_guard.resolve_path(source)
            dst_resolved = self.path_guard.resolve_path(destination)
            dst_resolved.parent.mkdir(parents=True, exist_ok=True)
            src_resolved.rename(dst_resolved)
            logger.info(f"move_file: {src_resolved} -> {dst_resolved}")
            return ToolResult(success=True, output={"source": str(src_resolved), "destination": str(dst_resolved)})
        except OSError as e:
            return ToolResult(success=False, error=str(e))


class CreateDirectoryTool(FilesystemToolBase):
    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="create_directory",
            description="Create a directory (and parents if needed). Requires authorization outside workspace.",
            category="filesystem",
            parameters_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Directory path to create."},
                },
                "required": ["path"],
            },
        )

    async def execute(self, arguments: dict, conversation_id: str) -> ToolResult:
        path = arguments.get("path", "")

        decision = self.security.check_file_operation(path, OperationType.WRITE)

        if self.security.is_denied(decision):
            return ToolResult(success=False, error=f"Access denied: {decision.reason}")

        if self.security.requires_approval(decision):
            approved, req_id = await self._request_permission(
                conversation_id=conversation_id,
                tool_name="create_directory",
                operation="WRITE",
                target=path,
                arguments=arguments,
                reason=f"Create directory outside workspace: {path}",
                risk_level=decision.risk_level.value,
            )
            if not approved:
                return ToolResult(success=False, error="Operation denied by user.", permission_request_id=req_id)

        try:
            resolved = self.path_guard.resolve_path(path)
            resolved.mkdir(parents=True, exist_ok=True)
            logger.info(f"create_directory: {resolved}")
            return ToolResult(success=True, output={"path": str(resolved)})
        except OSError as e:
            return ToolResult(success=False, error=str(e))


def create_filesystem_tools(security: SecurityPolicy, path_guard: PathGuard, ws_manager=None) -> list:
    """Factory function to create all filesystem tools."""
    args = (security, path_guard, ws_manager)
    return [
        ReadFileTool(*args),
        ListDirectoryTool(*args),
        SearchFilesTool(*args),
        WriteFileTool(*args),
        DeleteFileTool(*args),
        MoveFileTool(*args),
        CreateDirectoryTool(*args),
    ]

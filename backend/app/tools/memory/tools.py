"""Explicit long-term memory tool for the Odin agent (issue #27).

The agent loop already wires long-term memory automatically — recall before a
turn, write-back after it. This tool gives the model *explicit* control over
the same store so it can, on request (or when a fact is clearly durable), save
a memory, search it, list what is stored, update an entry or forget one.

Security classification
-----------------------
The tool only touches Odin's **own** long-term memory store (Mem0's embedded
vector store) — it resolves no filesystem path and runs no shell command. There
is no workspace boundary to enforce, so it is registered with
``requires_approval_by_default=False`` and never creates a permission request.
Memory is opt-in and off by default: when the store is unavailable the factory
registers no tool, and a defensively constructed tool still returns a clear
error instead of raising, so it can never take down a turn.
"""

from __future__ import annotations

import logging
from typing import Any

from app.agent.memory import MemoryService
from app.agent.memory.service import SOURCE_TOOL, MemoryRecord, _as_float
from app.tools.base import ToolDefinition, ToolResult

logger = logging.getLogger("odin.tools.memory")

_ACTIONS = ("save", "recall", "list", "update", "forget")


class MemoryTool:
    """Single agent tool exposing the long-term memory CRUD surface."""

    def __init__(self, memory: MemoryService | None) -> None:
        # ``None`` when memory is disabled or Mem0 is not installed. The factory
        # (``create_memory_tools``) then registers no tool at all, so a default
        # install keeps the exact tool surface it had before this feature; the
        # ``None`` branch below stays as a defensive guard.
        self.memory = memory

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="memory",
            description=(
                "Manage Odin's long-term memory (facts and preferences that "
                "persist across conversations). Actions: "
                "'save' a durable fact or preference; 'recall' memories by "
                "semantic search; 'list' stored memories; 'update' a memory's "
                "text; 'forget' (delete) a memory by id. Use it when the user "
                "explicitly asks to remember/forget something or asks what you "
                "remember. Requires ODIN_MEMORY_ENABLED=true."
            ),
            category="memory",
            # Odin's own store only — no filesystem/shell, so no approval gate.
            requires_approval_by_default=False,
            parameters_schema={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": list(_ACTIONS),
                        "description": "Operation to perform.",
                    },
                    "text": {
                        "type": "string",
                        "description": (
                            "Fact/preference to store ('save') or the new text "
                            "('update')."
                        ),
                    },
                    "query": {
                        "type": "string",
                        "description": "Search text for 'recall'.",
                    },
                    "id": {
                        "type": "string",
                        "description": "Memory id for 'update' / 'forget'.",
                    },
                    "origin": {
                        "type": "string",
                        "description": (
                            "Optional origin filter for 'list'/'recall' "
                            "(usually a conversation id)."
                        ),
                    },
                    "confidence": {
                        "type": "number",
                        "description": (
                            "Optional 0..1 confidence for the fact. Omitted "
                            "unless supplied (Mem0 has no confidence signal)."
                        ),
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum records to return for 'recall'/'list'.",
                    },
                },
                "required": ["action"],
            },
        )

    async def execute(self, arguments: dict, conversation_id: str) -> ToolResult:
        if self.memory is None:
            return ToolResult(
                success=False,
                error=(
                    "Long-term memory is disabled. Set ODIN_MEMORY_ENABLED=true "
                    "and install the optional Mem0 deps "
                    "(backend/requirements-memory.txt) to use it."
                ),
            )

        action = str(arguments.get("action") or "").strip().lower()
        if action == "save":
            return await self._save(arguments, conversation_id)
        if action == "recall":
            return await self._recall(arguments)
        if action == "list":
            return await self._list(arguments)
        if action == "update":
            return await self._update(arguments)
        if action == "forget":
            return await self._forget(arguments)
        return ToolResult(
            success=False,
            error=f"Unknown action '{action}'. Valid actions: {', '.join(_ACTIONS)}.",
        )

    # -- actions ------------------------------------------------------------
    async def _save(self, arguments: dict, conversation_id: str) -> ToolResult:
        text = str(arguments.get("text") or "").strip()
        if not text:
            return ToolResult(success=False, error="A 'text' is required to save a memory.")
        confidence = _as_float(arguments.get("confidence"))
        records = await self.memory.remember_text(
            text,
            # Record where the fact came from: the running conversation.
            origin=conversation_id,
            source=SOURCE_TOOL,
            confidence=confidence,
        )
        logger.info("memory save: %d record(s) written", len(records))
        # Report exactly what the store wrote: Mem0's extraction may decide the
        # fact is not durable and store nothing (count 0) — never claim a write
        # the backend did not make.
        return ToolResult(
            success=True,
            output={"saved": [_record_dict(r) for r in records], "count": len(records)},
        )

    async def _recall(self, arguments: dict) -> ToolResult:
        query = str(arguments.get("query") or "").strip()
        if not query:
            return ToolResult(
                success=False, error="A 'query' is required to recall memories."
            )
        records = await self.memory.recall_records(
            query,
            origin=_opt_str(arguments.get("origin")),
            limit=_opt_int(arguments.get("limit")),
        )
        return ToolResult(success=True, output=_memories_output(records))

    async def _list(self, arguments: dict) -> ToolResult:
        records = await self.memory.list_memories(
            origin=_opt_str(arguments.get("origin")),
            limit=_opt_int(arguments.get("limit")),
        )
        return ToolResult(success=True, output=_memories_output(records))

    async def _update(self, arguments: dict) -> ToolResult:
        memory_id = str(arguments.get("id") or "").strip()
        if not memory_id:
            return ToolResult(
                success=False, error="An 'id' is required to update a memory."
            )
        text = arguments.get("text")
        text = str(text).strip() if text is not None else None
        confidence = _as_float(arguments.get("confidence"))
        if not text and confidence is None:
            return ToolResult(
                success=False, error="Provide 'text' and/or 'confidence' to update."
            )
        ok = await self.memory.update(memory_id, text=text, confidence=confidence)
        if not ok:
            return ToolResult(
                success=False, error=f"Memory not found or not updated: {memory_id}"
            )
        return ToolResult(success=True, output={"id": memory_id, "updated": True})

    async def _forget(self, arguments: dict) -> ToolResult:
        memory_id = str(arguments.get("id") or "").strip()
        if not memory_id:
            return ToolResult(
                success=False, error="An 'id' is required to forget a memory."
            )
        ok = await self.memory.forget(memory_id)
        if not ok:
            return ToolResult(
                success=False, error=f"Memory not found or not deleted: {memory_id}"
            )
        return ToolResult(success=True, output={"id": memory_id, "forgotten": True})


def create_memory_tools(memory: MemoryService | None) -> list[MemoryTool]:
    """Factory for the long-term memory tool.

    Returns an **empty list** when ``memory`` is ``None`` (memory disabled or
    Mem0 not installed). A default install therefore exposes no dead tool: the
    agent schema and ``/api/tools`` are exactly as they were before this
    feature, honouring the "off by default behaves exactly as before"
    principle. When enabled, the single ``memory`` tool is registered in the
    ``main.py`` lifespan next to the others.
    """
    if memory is None:
        return []
    return [MemoryTool(memory)]


def _record_dict(record: MemoryRecord) -> dict:
    return record.to_dict()


def _memories_output(records: list[MemoryRecord]) -> dict:
    return {"memories": [_record_dict(r) for r in records], "count": len(records)}


def _opt_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _opt_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None

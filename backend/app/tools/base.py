from typing import Any, Protocol, runtime_checkable
from pydantic import BaseModel


class ToolResult(BaseModel):
    """Result returned by any tool execution."""

    success: bool
    output: Any = None
    error: str | None = None
    requires_approval: bool = False
    permission_request_id: str | None = None


class ToolDefinition(BaseModel):
    """Metadata about a tool, used for LLM function calling."""

    name: str
    description: str
    parameters_schema: dict  # JSON Schema
    category: str = "general"
    requires_approval_by_default: bool = False


@runtime_checkable
class BaseTool(Protocol):
    """Protocol that all tools must implement."""

    @property
    def definition(self) -> ToolDefinition: ...

    async def execute(
        self, arguments: dict, conversation_id: str
    ) -> ToolResult: ...

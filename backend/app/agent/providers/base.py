from typing import AsyncIterator, Protocol, runtime_checkable
from pydantic import BaseModel


class LLMMessage(BaseModel):
    """Normalized message format used internally."""

    role: str  # user | assistant | tool | system
    content: str = ""
    tool_calls: list[dict] | None = None  # [{id, name, arguments}]
    tool_call_id: str | None = None  # for tool result messages
    tool_name: str | None = None  # for tool result messages


class LLMChunk(BaseModel):
    """A streamed chunk from the LLM."""

    type: str  # text | tool_call | done | error
    content: str | None = None  # for text chunks
    tool_call_id: str | None = None  # for tool_call chunks
    tool_name: str | None = None
    tool_arguments: dict | None = None
    error: str | None = None


@runtime_checkable
class LLMProvider(Protocol):
    """Protocol for LLM providers. Implement this to add a new model."""

    async def generate(
        self,
        messages: list[LLMMessage],
        tools: list[dict],
        system: str,
    ) -> AsyncIterator[LLMChunk]:
        """Generate a response, yielding chunks as they arrive.

        Yields LLMChunk objects with type:
        - 'text': content is a string fragment
        - 'tool_call': tool_name, tool_call_id, tool_arguments are set
        - 'done': generation complete
        - 'error': error message
        """
        ...

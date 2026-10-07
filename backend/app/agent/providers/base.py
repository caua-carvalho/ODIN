"""Provider-agnostic LLM contracts.

These models are the only LLM-facing vocabulary the rest of the application
knows. Concrete providers (Gemini, Ollama, ...) translate between these
models and their own SDK/API formats.
"""

from typing import AsyncIterator, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, Field


class LLMToolCall(BaseModel):
    """A tool call requested by the model, in normalized form."""

    id: str
    name: str
    arguments: dict = Field(default_factory=dict)
    # Opaque provider-specific extras (never interpreted by the agent).
    # Carried across the loop so a provider can replay its own metadata
    # (e.g. Gemini thought signatures) on the next request.
    metadata: dict | None = None


class LLMMessage(BaseModel):
    """Normalized message format used internally."""

    role: Literal["user", "assistant", "tool", "system"]
    content: str = ""
    tool_calls: list[LLMToolCall] | None = None  # on assistant messages
    tool_call_id: str | None = None  # on tool result messages
    tool_name: str | None = None  # on tool result messages


class LLMTool(BaseModel):
    """Provider-agnostic tool definition."""

    name: str
    description: str
    parameters: dict = Field(default_factory=dict)  # JSON Schema


class LLMChunk(BaseModel):
    """A streamed chunk from the LLM."""

    type: Literal["text", "tool_call", "done", "error"]
    content: str | None = None  # for text chunks
    tool_call_id: str | None = None  # for tool_call chunks
    tool_name: str | None = None
    tool_arguments: dict | None = None
    metadata: dict | None = None  # opaque provider extras, see LLMToolCall
    error: str | None = None


@runtime_checkable
class LLMProvider(Protocol):
    """Protocol for LLM providers. Implement this to add a new model."""

    async def generate(
        self,
        messages: list[LLMMessage],
        tools: list[LLMTool],
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

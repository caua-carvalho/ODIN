"""Gemini LLM provider using the google-genai SDK.

Everything Gemini-specific lives here — including thought signatures,
which Gemini requires when replaying tool calls on follow-up requests.
"""

import base64
import logging
import uuid
from typing import AsyncIterator

from google import genai
from google.genai import types

from app.agent.providers.base import LLMChunk, LLMMessage, LLMTool
from app.config import settings

logger = logging.getLogger("odin.agent.providers.gemini")

# Key used to carry a Gemini thought_signature opaquely through the
# provider-agnostic layer (LLMToolCall.metadata / LLMChunk.metadata).
THOUGHT_SIGNATURE_KEY = "thought_signature"


def _build_gemini_contents(messages: list[LLMMessage]) -> list[types.Content]:
    """Convert internal messages to Gemini Content format."""
    contents = []

    for msg in messages:
        if msg.role == "system":
            continue  # system handled via system_instruction

        if msg.role == "user":
            contents.append(
                types.Content(
                    role="user",
                    parts=[types.Part.from_text(text=msg.content)],
                )
            )

        elif msg.role == "assistant":
            parts = []
            if msg.content:
                parts.append(types.Part.from_text(text=msg.content))
            if msg.tool_calls:
                for tc in msg.tool_calls:
                    part = types.Part.from_function_call(
                        name=tc.name,
                        args=tc.arguments or {},
                    )
                    # Gemini rejects function calls that were originally
                    # returned with a thought_signature but are replayed
                    # without it. Restore it from the opaque metadata.
                    signature = (tc.metadata or {}).get(THOUGHT_SIGNATURE_KEY)
                    if signature:
                        part.thought_signature = base64.b64decode(signature)
                    parts.append(part)
            if parts:
                contents.append(types.Content(role="model", parts=parts))

        elif msg.role == "tool":
            # Tool result - must follow the assistant message that made the call
            contents.append(
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_function_response(
                            name=msg.tool_name or "tool",
                            response={"result": msg.content},
                        )
                    ],
                )
            )

    return contents


def _build_gemini_tools(tools: list[LLMTool]) -> list[types.Tool]:
    """Convert generic tool definitions to Gemini Tool format."""
    if not tools:
        return []

    declarations = []
    for tool in tools:
        schema = tool.parameters or None
        declarations.append(
            types.FunctionDeclaration(
                name=tool.name,
                description=tool.description,
                parameters=schema,
            )
        )

    return [types.Tool(function_declarations=declarations)]


def _tool_call_chunk(part: types.Part) -> LLMChunk:
    """Normalize a Gemini functionCall part into an LLMChunk."""
    fc = part.function_call

    metadata = None
    signature = getattr(part, "thought_signature", None)
    if signature:
        if isinstance(signature, str):
            signature = signature.encode("utf-8")
        metadata = {
            THOUGHT_SIGNATURE_KEY: base64.b64encode(signature).decode("ascii")
        }

    args = dict(fc.args) if fc.args else {}
    return LLMChunk(
        type="tool_call",
        tool_call_id=str(uuid.uuid4()),  # Gemini doesn't issue tool call ids
        tool_name=fc.name,
        tool_arguments=args,
        metadata=metadata,
    )


class GeminiProvider:
    """Gemini LLM provider using google-genai SDK."""

    def __init__(self, model: str | None = None, api_key: str | None = None) -> None:
        api_key = api_key if api_key is not None else settings.gemini_api_key
        if not api_key:
            raise ValueError("GEMINI_API_KEY not configured")
        self.client = genai.Client(api_key=api_key)
        self.model = model or settings.odin_model
        logger.info(f"GeminiProvider initialized with model: {self.model}")

    async def generate(
        self,
        messages: list[LLMMessage],
        tools: list[LLMTool],
        system: str,
    ) -> AsyncIterator[LLMChunk]:
        """Generate response from Gemini, yielding chunks."""
        contents = _build_gemini_contents(messages)
        gemini_tools = _build_gemini_tools(tools)

        config = types.GenerateContentConfig(
            system_instruction=system if system else None,
            tools=gemini_tools if gemini_tools else None,
            temperature=0.7,
        )

        try:
            # Use streaming for text responses
            response_stream = await self.client.aio.models.generate_content_stream(
                model=self.model,
                contents=contents,
                config=config,
            )

            async for chunk in response_stream:
                if not chunk.candidates:
                    continue

                for candidate in chunk.candidates:
                    if not candidate.content or not candidate.content.parts:
                        continue

                    for part in candidate.content.parts:
                        if hasattr(part, "text") and part.text:
                            yield LLMChunk(type="text", content=part.text)

                        elif hasattr(part, "function_call") and part.function_call:
                            yield _tool_call_chunk(part)

            yield LLMChunk(type="done")

        except Exception as e:
            logger.error(f"Gemini generation error: {e}", exc_info=True)
            yield LLMChunk(type="error", error=str(e))

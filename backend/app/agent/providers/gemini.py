import logging
import uuid
from typing import AsyncIterator

from google import genai
from google.genai import types

from app.agent.providers.base import LLMChunk, LLMMessage
from app.config import settings

logger = logging.getLogger("odin.agent.providers.gemini")


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
                    parts.append(
                        types.Part.from_function_call(
                            name=tc["name"],
                            args=tc.get("arguments", {}),
                        )
                    )
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


def _build_gemini_tools(tools: list[dict]) -> list[types.Tool]:
    """Convert tool definitions to Gemini Tool format."""
    if not tools:
        return []

    declarations = []
    for tool in tools:
        schema = tool.get("parameters", {})
        # Gemini expects the schema in a specific format
        declarations.append(
            types.FunctionDeclaration(
                name=tool["name"],
                description=tool.get("description", ""),
                parameters=schema if schema else None,
            )
        )

    return [types.Tool(function_declarations=declarations)]


class GeminiProvider:
    """Gemini LLM provider using google-genai SDK."""

    def __init__(self) -> None:
        if not settings.gemini_api_key:
            raise ValueError("GEMINI_API_KEY not configured")
        self.client = genai.Client(api_key=settings.gemini_api_key)
        self.model = settings.odin_model
        logger.info(f"GeminiProvider initialized with model: {self.model}")

    async def generate(
        self,
        messages: list[LLMMessage],
        tools: list[dict],
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

            text_buffer = ""
            function_calls = []

            async for chunk in response_stream:
                if not chunk.candidates:
                    continue

                for candidate in chunk.candidates:
                    if not candidate.content or not candidate.content.parts:
                        continue

                    for part in candidate.content.parts:
                        if hasattr(part, "text") and part.text:
                            text_buffer += part.text
                            yield LLMChunk(type="text", content=part.text)

                        elif hasattr(part, "function_call") and part.function_call:
                            fc = part.function_call
                            call_id = str(uuid.uuid4())
                            args = dict(fc.args) if fc.args else {}
                            function_calls.append(
                                {
                                    "id": call_id,
                                    "name": fc.name,
                                    "arguments": args,
                                }
                            )
                            yield LLMChunk(
                                type="tool_call",
                                tool_call_id=call_id,
                                tool_name=fc.name,
                                tool_arguments=args,
                            )

            yield LLMChunk(type="done")

        except Exception as e:
            logger.error(f"Gemini generation error: {e}", exc_info=True)
            yield LLMChunk(type="error", error=str(e))

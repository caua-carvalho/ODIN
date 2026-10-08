"""Ollama LLM provider using the local HTTP API (httpx, already a dependency)."""

import json
import logging
import uuid
from typing import AsyncIterator

import httpx

from app.agent.providers.base import LLMChunk, LLMMessage, LLMTool
from app.config import settings

logger = logging.getLogger("odin.agent.providers.ollama")

# Seconds allowed for the server to stream the next chunk (not total time).
STREAM_TIMEOUT = 120.0


def _build_ollama_messages(messages: list[LLMMessage], system: str) -> list[dict]:
    """Convert internal messages to Ollama chat message format."""
    out: list[dict] = []

    if system:
        out.append({"role": "system", "content": system})

    for msg in messages:
        if msg.role == "system":
            continue  # system handled above

        elif msg.role == "user":
            out.append({"role": "user", "content": msg.content})

        elif msg.role == "assistant":
            entry: dict = {"role": "assistant", "content": msg.content}
            if msg.tool_calls:
                entry["tool_calls"] = [
                    {"function": {"name": tc.name, "arguments": tc.arguments or {}}}
                    for tc in msg.tool_calls
                ]
            out.append(entry)

        elif msg.role == "tool":
            # Tool result follows the assistant message that made the call.
            entry = {"role": "tool", "content": msg.content}
            if msg.tool_name:
                entry["tool_name"] = msg.tool_name
            out.append(entry)

    return out


def _build_ollama_tools(tools: list[LLMTool]) -> list[dict]:
    """Convert generic tool definitions to Ollama tool format."""
    return [
        {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters
                or {"type": "object", "properties": {}},
            },
        }
        for tool in tools
    ]


def _chunks_from_event(data: dict) -> list[LLMChunk]:
    """Normalize one streamed Ollama event into LLMChunks."""
    chunks: list[LLMChunk] = []

    message = data.get("message") or {}

    content = message.get("content") or ""
    if content:
        chunks.append(LLMChunk(type="text", content=content))

    for tc in message.get("tool_calls") or []:
        fn = tc.get("function") or {}
        args = fn.get("arguments") or {}
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except json.JSONDecodeError:
                args = {"raw": args}
        chunks.append(
            LLMChunk(
                type="tool_call",
                tool_call_id=str(uuid.uuid4()),  # Ollama doesn't issue ids
                tool_name=fn.get("name") or "",
                tool_arguments=args,
            )
        )

    return chunks


class OllamaProvider:
    """LLM provider for local Ollama models via /api/chat."""

    def __init__(
        self,
        model: str | None = None,
        base_url: str | None = None,
        think: bool | None = None,
    ) -> None:
        self.model = model or settings.odin_model
        self.base_url = (base_url or settings.ollama_base_url).rstrip("/")
        self.think = settings.ollama_think if think is None else think
        if not self.base_url:
            raise ValueError("OLLAMA_BASE_URL not configured")
        logger.info(f"OllamaProvider initialized with model: {self.model}")

    async def generate(
        self,
        messages: list[LLMMessage],
        tools: list[LLMTool],
        system: str,
    ) -> AsyncIterator[LLMChunk]:
        """Generate response from Ollama, yielding chunks."""
        payload: dict = {
            "model": self.model,
            "messages": _build_ollama_messages(messages, system),
            "stream": True,
            "think": self.think,
            "options": {"temperature": 0.7},
        }
        ollama_tools = _build_ollama_tools(tools)
        if ollama_tools:
            payload["tools"] = ollama_tools

        try:
            async with httpx.AsyncClient(
                base_url=self.base_url,
                timeout=httpx.Timeout(STREAM_TIMEOUT, connect=10.0),
            ) as client:
                async with client.stream("POST", "/api/chat", json=payload) as response:
                    if response.status_code != 200:
                        body = (await response.aread()).decode("utf-8", errors="replace")
                        logger.error(
                            f"Ollama error {response.status_code}: {body[:500]}"
                        )
                        yield LLMChunk(
                            type="error",
                            error=f"Ollama request failed "
                            f"({response.status_code}): {body[:500]}",
                        )
                        return

                    async for line in response.aiter_lines():
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            data = json.loads(line)
                        except json.JSONDecodeError:
                            continue

                        if data.get("error"):
                            yield LLMChunk(type="error", error=str(data["error"]))
                            return

                        for chunk in _chunks_from_event(data):
                            yield chunk

                        if data.get("done"):
                            break

            yield LLMChunk(type="done")

        except httpx.HTTPError as e:
            logger.error(f"Ollama connection error: {e}", exc_info=True)
            yield LLMChunk(
                type="error",
                error=f"Could not reach Ollama at {self.base_url}: {e}",
            )
        except Exception as e:
            logger.error(f"Ollama generation error: {e}", exc_info=True)
            yield LLMChunk(type="error", error=str(e))

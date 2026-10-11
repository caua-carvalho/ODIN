"""Groq LLM provider using Groq's OpenAI-compatible HTTP API (httpx).

Groq exposes an OpenAI-compatible `/chat/completions` endpoint, so the request
and response shapes mirror OpenAI's. Streamed tool calls arrive as incremental
deltas that must be accumulated before the agent can execute them.
"""

import json
import logging
import uuid
from typing import AsyncIterator

import httpx

from app.agent.providers.base import LLMChunk, LLMMessage, LLMTool
from app.config import settings

logger = logging.getLogger("odin.agent.providers.groq")

# Seconds allowed for the server to stream the next chunk (not total time).
STREAM_TIMEOUT = 120.0


def _build_groq_messages(messages: list[LLMMessage], system: str) -> list[dict]:
    """Convert internal messages to Groq (OpenAI-compatible) chat format."""
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
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments or {}),
                        },
                    }
                    for tc in msg.tool_calls
                ]
            out.append(entry)

        elif msg.role == "tool":
            # Tool result follows the assistant message that made the call and
            # must reference the originating tool_call_id.
            out.append(
                {
                    "role": "tool",
                    "tool_call_id": msg.tool_call_id or "",
                    "content": msg.content,
                }
            )

    return out


def _build_groq_tools(tools: list[LLMTool]) -> list[dict]:
    """Convert generic tool definitions to Groq (OpenAI) tool format."""
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


def _finalize_tool_calls(states: dict[int, dict]) -> list[LLMChunk]:
    """Flatten accumulated streaming tool-call deltas into complete chunks."""
    chunks: list[LLMChunk] = []
    for index in sorted(states):
        state = states[index]
        raw_args = state.get("arguments") or ""
        if raw_args:
            try:
                arguments = json.loads(raw_args)
            except json.JSONDecodeError:
                arguments = {"raw": raw_args}
        else:
            arguments = {}
        chunks.append(
            LLMChunk(
                type="tool_call",
                tool_call_id=state.get("id") or str(uuid.uuid4()),
                tool_name=state.get("name") or "",
                tool_arguments=arguments,
            )
        )
    return chunks


class GroqProvider:
    """LLM provider for Groq models via the OpenAI-compatible API."""

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> None:
        self.api_key = api_key if api_key is not None else settings.groq_api_key
        if not self.api_key:
            raise ValueError("GROQ_API_KEY not configured")
        self.base_url = (base_url or settings.groq_base_url).rstrip("/")
        self.model = model or settings.odin_model
        logger.info(f"GroqProvider initialized with model: {self.model}")

    async def generate(
        self,
        messages: list[LLMMessage],
        tools: list[LLMTool],
        system: str,
    ) -> AsyncIterator[LLMChunk]:
        """Generate response from Groq, yielding chunks."""
        payload: dict = {
            "model": self.model,
            "messages": _build_groq_messages(messages, system),
            "stream": True,
            "temperature": 0.7,
        }
        groq_tools = _build_groq_tools(tools)
        if groq_tools:
            payload["tools"] = groq_tools

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        # Tool calls stream as fragments keyed by index; accumulate them and
        # only emit once the stream ends so the agent receives complete args.
        tool_states: dict[int, dict] = {}

        try:
            async with httpx.AsyncClient(
                base_url=self.base_url,
                timeout=httpx.Timeout(STREAM_TIMEOUT, connect=10.0),
            ) as client:
                async with client.stream(
                    "POST", "/chat/completions", json=payload, headers=headers
                ) as response:
                    if response.status_code != 200:
                        body = (await response.aread()).decode(
                            "utf-8", errors="replace"
                        )
                        logger.error(
                            f"Groq error {response.status_code}: {body[:500]}"
                        )
                        yield LLMChunk(
                            type="error",
                            error=f"Groq request failed "
                            f"({response.status_code}): {body[:500]}",
                        )
                        return

                    async for line in response.aiter_lines():
                        line = line.strip()
                        if not line or not line.startswith("data:"):
                            continue
                        data_str = line[len("data:") :].strip()
                        if not data_str or data_str == "[DONE]":
                            continue
                        try:
                            data = json.loads(data_str)
                        except json.JSONDecodeError:
                            continue

                        if data.get("error"):
                            error = data["error"]
                            message = (
                                error.get("message")
                                if isinstance(error, dict)
                                else str(error)
                            )
                            yield LLMChunk(type="error", error=str(message))
                            return

                        choices = data.get("choices") or []
                        if not choices:
                            continue
                        delta = choices[0].get("delta") or {}

                        content = delta.get("content")
                        if content:
                            yield LLMChunk(type="text", content=content)

                        for tc in delta.get("tool_calls") or []:
                            idx = tc.get("index", 0)
                            state = tool_states.setdefault(
                                idx, {"id": None, "name": "", "arguments": ""}
                            )
                            if tc.get("id"):
                                state["id"] = tc["id"]
                            fn = tc.get("function") or {}
                            if fn.get("name"):
                                state["name"] = fn["name"]
                            if fn.get("arguments"):
                                state["arguments"] += fn["arguments"]

            for chunk in _finalize_tool_calls(tool_states):
                yield chunk

            yield LLMChunk(type="done")

        except httpx.HTTPError as e:
            logger.error(f"Groq connection error: {e}", exc_info=True)
            yield LLMChunk(
                type="error",
                error=f"Could not reach Groq at {self.base_url}: {e}",
            )
        except Exception as e:
            logger.error(f"Groq generation error: {e}", exc_info=True)
            yield LLMChunk(type="error", error=str(e))

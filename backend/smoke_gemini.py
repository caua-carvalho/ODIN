"""Manual smoke test: real Gemini provider (text + tool call round-trip)."""
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.agent.providers import create_llm_provider
from app.agent.providers.base import LLMMessage, LLMTool, LLMToolCall
from app.config import Settings


async def main() -> None:
    # Read the Gemini config explicitly — the active .env may be set to ollama.
    env_path = Path(__file__).parent.parent / ".env"
    env_vars = {}
    for line in env_path.read_text().splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.split("=", 1)
            env_vars[k.strip()] = v.strip()
    settings = Settings(
        odin_model_provider="gemini",
        odin_model=os.environ.get("SMOKE_GEMINI_MODEL", "gemini-2.0-flash"),
        gemini_api_key=env_vars.get("GEMINI_API_KEY", ""),
        _env_file=None,
    )
    print(f"provider={settings.odin_model_provider} model={settings.odin_model}")
    provider = create_llm_provider(settings)
    print(f"provider class={provider.__class__.__name__}")

    tool = LLMTool(
        name="list_directory",
        description="List files in a directory",
        parameters={
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    )

    messages = [LLMMessage(role="user", content="List the files in /tmp, please.")]

    print("--- iteration 1 ---")
    text = ""
    calls: list[LLMToolCall] = []
    async for chunk in provider.generate(messages=messages, tools=[tool], system="You are Odin. Use tools when needed."):
        if chunk.type == "text":
            text += chunk.content or ""
        elif chunk.type == "tool_call":
            calls.append(
                LLMToolCall(
                    id=chunk.tool_call_id,
                    name=chunk.tool_name,
                    arguments=chunk.tool_arguments,
                    metadata=chunk.metadata,
                )
            )
        elif chunk.type == "error":
            print("ERROR:", chunk.error)
            sys.exit(1)
    print(f"text={text[:120]!r}")
    print(f"tool_calls={[c.model_dump() for c in calls]}")
    assert calls, "expected at least one tool call"

    messages.append(LLMMessage(role="assistant", content=text, tool_calls=calls))
    messages.append(
        LLMMessage(
            role="tool",
            content='{"files": ["a.txt", "b.txt"]}',
            tool_call_id=calls[0].id,
            tool_name=calls[0].name,
        )
    )

    print("--- iteration 2 (after tool result; replays thought_signature) ---")
    text2 = ""
    async for chunk in provider.generate(messages=messages, tools=[tool], system="You are Odin. Use tools when needed."):
        if chunk.type == "text":
            text2 += chunk.content or ""
        elif chunk.type == "error":
            print("ERROR:", chunk.error)
            sys.exit(1)
    print(f"text={text2[:300]!r}")
    assert text2, "expected a final answer after tool result"
    print("GEMINI SMOKE TEST OK")


if __name__ == "__main__":
    asyncio.run(main())

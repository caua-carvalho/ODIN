"""Manual smoke test: real Ollama provider with qwen3:0.6b (text + tool call)."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.agent.providers import create_llm_provider
from app.agent.providers.base import LLMMessage, LLMTool, LLMToolCall
from app.config import Settings


async def main() -> None:
    settings = Settings(
        odin_model_provider="ollama",
        odin_model="qwen3:0.6b",
        ollama_base_url="http://localhost:11434",
        _env_file=None,
    )
    provider = create_llm_provider(settings)
    print(f"provider={provider.__class__.__name__} model={provider.model}")

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

    # Feed the tool result back (history reconstruction)
    messages.append(LLMMessage(role="assistant", content=text, tool_calls=calls))
    messages.append(
        LLMMessage(
            role="tool",
            content='{"files": ["a.txt", "b.txt"]}',
            tool_call_id=calls[0].id,
            tool_name=calls[0].name,
        )
    )

    print("--- iteration 2 (after tool result) ---")
    text2 = ""
    calls2 = []
    async for chunk in provider.generate(messages=messages, tools=[tool], system="You are Odin. Use tools when needed."):
        if chunk.type == "text":
            text2 += chunk.content or ""
        elif chunk.type == "tool_call":
            calls2.append(chunk.tool_name)
        elif chunk.type == "error":
            print("ERROR:", chunk.error)
            sys.exit(1)
    print(f"text={text2[:300]!r}")
    print(f"extra_tool_calls={calls2}")
    assert text2, "expected a final answer after tool result"
    print("OLLAMA SMOKE TEST OK")


if __name__ == "__main__":
    asyncio.run(main())

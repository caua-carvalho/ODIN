"""Manual smoke test: full OdinAgent loop against real Ollama.

Covers: user msg -> LLM -> tool call -> tool execution -> tool result -> LLM -> done,
with persistence (DB) in the middle.
"""
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

os.environ["ODIN_MODEL_PROVIDER"] = "ollama"
os.environ["ODIN_MODEL"] = "qwen3:0.6b"
os.environ["OLLAMA_BASE_URL"] = "http://localhost:11434"
os.environ["GEMINI_API_KEY"] = ""
os.environ["ODIN_WORKSPACE"] = "/tmp/odin-smoke-workspace"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./smoke_agent.db"

import logging

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

from app.main import lifespan, app, odin_agent  # noqa: E402
import app.main as main_mod  # noqa: E402
from contextlib import asynccontextmanager  # noqa: E402

Path(os.environ["ODIN_WORKSPACE"]).mkdir(parents=True, exist_ok=True)
(Path(os.environ["ODIN_WORKSPACE"]) / "hello.txt").write_text("hello from odin\n")


async def run() -> None:
    # Reuse the real application bootstrap (lifespan)
    async with lifespan(app):
        agent = main_mod.odin_agent
        assert agent is not None
        print(f"provider={type(agent.provider).__name__} model={agent.provider.model}")

        events = []
        async for event in agent.chat(
            message="List the files in my workspace using the list_directory tool.",
            conversation_id="smoke-conv-1",
        ):
            events.append(event)
            kind = event.get("type")
            if kind == "text_chunk":
                print("TEXT:", (event.get("content") or "")[:80], end=" ")
            else:
                print(kind, event.get("tool") or event.get("message") or "")

        types = [e["type"] for e in events]
        assert "tool_start" in types, "expected a tool call in the agent loop"
        assert "tool_end" in types, "expected tool execution"
        assert types[-1] == "done", types
        tool_names = {e.get("tool") for e in events if e["type"] == "tool_start"}
        print("tools executed:", tool_names)
        print("AGENT LOOP SMOKE TEST OK")


if __name__ == "__main__":
    asyncio.run(run())

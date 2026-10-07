"""Manual smoke test: FastAPI bootstrap with Ollama (lifespan + health)."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

# Configure Ollama BEFORE importing the app
os.environ["ODIN_MODEL_PROVIDER"] = "ollama"
os.environ["ODIN_MODEL"] = "qwen3:0.6b"
os.environ["OLLAMA_BASE_URL"] = "http://localhost:11434"
os.environ["GEMINI_API_KEY"] = ""  # must NOT be required when using ollama
os.environ["ODIN_WORKSPACE"] = "/tmp/odin-smoke-workspace"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./smoke_bootstrap.db"

from fastapi.testclient import TestClient

import app.main as main_mod

Path(os.environ["ODIN_WORKSPACE"]).mkdir(parents=True, exist_ok=True)

with TestClient(main_mod.app) as client:
    health = client.get("/api/health").json()
    print("HEALTH:", health)

    assert health["status"] == "online"
    assert health["model_provider"] == "ollama"
    assert health["model"] == "qwen3:0.6b"
    assert health["agent_ready"] is True
    assert health["tools_count"] > 0

    agent = main_mod.odin_agent
    from app.agent.providers import LLMProvider
    from app.agent.providers.ollama import OllamaProvider

    assert isinstance(agent.provider, OllamaProvider)
    assert isinstance(agent.provider, LLMProvider)
    print("provider:", type(agent.provider).__name__, agent.provider.model)

    # Provider must be provider-agnostic in the agent
    from app.tools.registry import ToolRegistry
    tools = agent.tool_registry.to_llm_tools()
    print("tools:", [t.name for t in tools])
    assert all(isinstance(t, type(tools[0])) for t in tools)

print("BOOTSTRAP SMOKE TEST OK")

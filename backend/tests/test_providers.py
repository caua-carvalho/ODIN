"""Provider architecture tests.

Covers the pieces that are provider-agnostic: the ``LLMProvider`` contract, the
tool registry bridge, message round-tripping (tool-call history reloaded from
the DB), configuration and factory selection.

Adapter internals (message/tool conversion, streamed tool-call accumulation,
provider extras) live in ``test_litellm_provider.py``.
"""
import inspect
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

# Make sure we can import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

os.environ.setdefault("GEMINI_API_KEY", "test-key")

from app.agent.providers import create_llm_provider
from app.agent.providers.base import (
    LLMMessage,
    LLMProvider,
    LLMTool,
    LLMToolCall,
)
from app.agent.providers.litellm_provider import LiteLLMProvider
from app.config import Settings
from app.tools.registry import ToolRegistry

GENERIC_TOOL = LLMTool(
    name="list_directory",
    description="List files",
    parameters={"type": "object", "properties": {}},
)


# ---------------------------------------------------------------------------
# Provider abstraction / contract
# ---------------------------------------------------------------------------
class TestProviderContract:
    def test_protocol_signature(self):
        sig = inspect.signature(LLMProvider.generate)
        assert list(sig.parameters) == ["self", "messages", "tools", "system"]

    def test_litellm_implements_protocol(self):
        provider = LiteLLMProvider(model="m", provider="openai", api_key="k")
        assert isinstance(provider, LLMProvider)

    def test_generate_signature_matches(self):
        sig = inspect.signature(LiteLLMProvider.generate)
        assert list(sig.parameters) == ["self", "messages", "tools", "system"]
        assert inspect.isasyncgenfunction(LiteLLMProvider.generate)


# ---------------------------------------------------------------------------
# Tool registry bridge
# ---------------------------------------------------------------------------
class TestToolRegistry:
    def test_tool_registry_returns_llm_tools(self):
        registry = ToolRegistry()

        class FakeTool:
            definition = SimpleNamespace(
                name="list_directory",
                description="List files",
                parameters_schema={"type": "object", "properties": {}},
            )

        registry.register(FakeTool())
        tools = registry.to_llm_tools()

        assert tools == [GENERIC_TOOL]
        assert all(isinstance(t, LLMTool) for t in tools)
        assert not hasattr(registry, "to_gemini_tools")


# ---------------------------------------------------------------------------
# Tool call history round-trip
# ---------------------------------------------------------------------------
class TestToolCallHistory:
    def test_llm_message_coerces_dict_tool_calls(self):
        """History reloaded from the DB (raw JSON dicts) must validate."""
        msg = LLMMessage.model_validate(
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"id": "call_1", "name": "list_directory", "arguments": {"path": "/tmp"}}
                ],
            }
        )
        assert isinstance(msg.tool_calls[0], LLMToolCall)
        assert msg.tool_calls[0].name == "list_directory"


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
class TestConfiguration:
    def test_provider_and_model_from_env(self, monkeypatch):
        monkeypatch.setenv("ODIN_MODEL_PROVIDER", "ollama")
        monkeypatch.setenv("ODIN_MODEL", "qwen3:0.6b")
        monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434")
        s = Settings(_env_file=None)
        assert s.odin_model_provider == "ollama"
        assert s.odin_model == "qwen3:0.6b"
        assert s.ollama_base_url == "http://localhost:11434"

    def test_gemini_config_from_env(self, monkeypatch):
        monkeypatch.setenv("ODIN_MODEL_PROVIDER", "gemini")
        monkeypatch.setenv("ODIN_MODEL", "gemini-2.5-flash")
        monkeypatch.setenv("GEMINI_API_KEY", "abc123")
        s = Settings(_env_file=None)
        assert s.odin_model_provider == "gemini"
        assert s.odin_model == "gemini-2.5-flash"
        assert s.gemini_api_key == "abc123"

    def test_unused_provider_config_not_required(self, monkeypatch):
        """Choosing ollama must not require GEMINI_API_KEY."""
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        s = Settings(
            odin_model_provider="ollama",
            odin_model="qwen3:0.6b",
            gemini_api_key="",
            _env_file=None,
        )
        provider = create_llm_provider(s)
        assert isinstance(provider, LiteLLMProvider)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------
class TestFactory:
    def test_creates_ollama_provider(self):
        s = Settings(
            odin_model_provider="ollama", odin_model="qwen3:0.6b", _env_file=None
        )
        provider = create_llm_provider(s)
        assert isinstance(provider, LiteLLMProvider)
        assert provider.model == "qwen3:0.6b"
        assert provider.litellm_model == "ollama/qwen3:0.6b"
        assert provider.api_base == "http://localhost:11434"

    def test_creates_gemini_provider(self):
        s = Settings(
            odin_model_provider="gemini",
            odin_model="gemini-2.5-flash",
            gemini_api_key="test-key",
            _env_file=None,
        )
        provider = create_llm_provider(s)
        assert isinstance(provider, LiteLLMProvider)
        assert provider.model == "gemini-2.5-flash"
        assert provider.litellm_model == "gemini/gemini-2.5-flash"
        assert provider.api_key == "test-key"

    def test_creates_groq_provider(self):
        s = Settings(
            odin_model_provider="groq",
            odin_model="openai/gpt-oss-120b",
            groq_api_key="test-key",
            _env_file=None,
        )
        provider = create_llm_provider(s)
        assert isinstance(provider, LiteLLMProvider)
        assert provider.model == "openai/gpt-oss-120b"
        # Groq model ids already contain a slash; the vendor prefix is added.
        assert provider.litellm_model == "groq/openai/gpt-oss-120b"
        assert provider.api_base == "https://api.groq.com/openai/v1"

    def test_creates_openai_provider(self):
        s = Settings(
            odin_model_provider="openai",
            odin_model="gpt-4o-mini",
            openai_api_key="test-key",
            _env_file=None,
        )
        provider = create_llm_provider(s)
        assert isinstance(provider, LiteLLMProvider)
        assert provider.litellm_model == "openai/gpt-4o-mini"

    def test_model_already_prefixed_is_not_double_prefixed(self):
        s = Settings(
            odin_model_provider="gemini",
            odin_model="gemini/gemini-2.5-flash",
            gemini_api_key="test-key",
            _env_file=None,
        )
        provider = create_llm_provider(s)
        assert provider.litellm_model == "gemini/gemini-2.5-flash"

    def test_groq_without_api_key_raises(self):
        s = Settings(
            odin_model_provider="groq",
            groq_api_key="",
            _env_file=None,
        )
        with pytest.raises(ValueError, match="GROQ_API_KEY"):
            create_llm_provider(s)

    def test_provider_name_is_normalized(self):
        s = Settings(
            odin_model_provider="  OLLAMA ",
            odin_model="qwen3:0.6b",
            _env_file=None,
        )
        provider = create_llm_provider(s)
        assert isinstance(provider, LiteLLMProvider)
        assert provider.provider == "ollama"

    def test_unknown_provider_raises_explicit_error(self):
        s = Settings(odin_model_provider="xyz", _env_file=None)
        with pytest.raises(ValueError) as exc:
            create_llm_provider(s)
        message = str(exc.value)
        assert "Unsupported LLM provider: xyz" in message
        # The message lists the real, catalog-derived provider set.
        for name in ("gemini", "groq", "ollama", "openai", "anthropic"):
            assert name in message

    def test_gemini_without_api_key_raises(self):
        s = Settings(
            odin_model_provider="gemini",
            gemini_api_key="",
            _env_file=None,
        )
        with pytest.raises(ValueError, match="GEMINI_API_KEY"):
            create_llm_provider(s)

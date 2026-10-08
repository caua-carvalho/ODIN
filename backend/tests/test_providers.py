"""LLM provider architecture tests.

Covers: provider contract, tool/tool-call normalization, configuration,
factory selection, and message round-tripping (tool call history).
"""
import inspect
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from pydantic import BaseModel

# Make sure we can import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

os.environ.setdefault("GEMINI_API_KEY", "test-key")

from app.agent.providers import create_llm_provider
from app.agent.providers.base import (
    LLMChunk,
    LLMMessage,
    LLMProvider,
    LLMTool,
    LLMToolCall,
)
from app.agent.providers.gemini import (
    GeminiProvider,
    _build_gemini_contents,
    _build_gemini_tools,
    _tool_call_chunk,
)
from app.agent.providers.ollama import (
    OllamaProvider,
    _build_ollama_messages,
    _build_ollama_tools,
    _chunks_from_event,
)
from app.config import Settings
from app.tools.registry import ToolRegistry
from google.genai import types

GENERIC_TOOL = LLMTool(
    name="list_directory",
    description="List files",
    parameters={"type": "object", "properties": {}},
)


# ---------------------------------------------------------------------------
# Provider abstraction / contract
# ---------------------------------------------------------------------------
class TestProviderContract:
    def test_gemini_implements_protocol(self):
        provider = GeminiProvider(model="gemini-2.0-flash", api_key="test-key")
        assert isinstance(provider, LLMProvider)

    def test_ollama_implements_protocol(self):
        provider = OllamaProvider(model="qwen3:0.6b", base_url="http://localhost:11434")
        assert isinstance(provider, LLMProvider)

    def test_generate_signatures_match(self):
        """Both providers must expose the exact same generate() contract."""
        expected = ["self", "messages", "tools", "system"]
        for cls in (GeminiProvider, OllamaProvider):
            sig = inspect.signature(cls.generate)
            assert list(sig.parameters) == expected, cls.__name__
            assert inspect.isasyncgenfunction(cls.generate), cls.__name__

    def test_protocol_signature(self):
        sig = inspect.signature(LLMProvider.generate)
        assert list(sig.parameters) == ["self", "messages", "tools", "system"]


# ---------------------------------------------------------------------------
# Tool conversion (LLMTool -> provider format)
# ---------------------------------------------------------------------------
class TestToolConversion:
    def test_gemini_tool_conversion(self):
        result = _build_gemini_tools([GENERIC_TOOL])
        declaration = result[0].function_declarations[0]
        assert declaration.name == "list_directory"
        assert declaration.description == "List files"
        assert declaration.parameters is not None

    def test_ollama_tool_conversion(self):
        result = _build_ollama_tools([GENERIC_TOOL])
        assert result == [
            {
                "type": "function",
                "function": {
                    "name": "list_directory",
                    "description": "List files",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ]

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
# Tool call normalization (provider response -> LLMToolCall)
# ---------------------------------------------------------------------------
class TestToolCallNormalization:
    def test_gemini_function_call_normalized(self):
        part = types.Part(
            function_call=types.FunctionCall(
                name="list_directory", args={"path": "/tmp"}
            ),
            thought_signature=b"original-signature",
        )
        chunk = _tool_call_chunk(part)

        call = LLMToolCall(
            id=chunk.tool_call_id,
            name=chunk.tool_name,
            arguments=chunk.tool_arguments,
            metadata=chunk.metadata,
        )
        assert chunk.type == "tool_call"
        assert call.name == "list_directory"
        assert call.arguments == {"path": "/tmp"}
        assert call.id
        # Gemini thought_signature stays encapsulated in provider metadata
        assert chunk.metadata is not None
        assert "thought_signature" in chunk.metadata

    def test_gemini_function_call_without_signature(self):
        part = types.Part(
            function_call=types.FunctionCall(name="read_file", args={})
        )
        chunk = _tool_call_chunk(part)
        assert chunk.metadata is None

    def test_ollama_tool_call_normalized(self):
        event = {
            "message": {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "function": {
                            "name": "list_directory",
                            "arguments": {"path": "/tmp"},
                        }
                    }
                ],
            },
            "done": False,
        }
        chunks = _chunks_from_event(event)
        assert len(chunks) == 1

        call = LLMToolCall(
            id=chunks[0].tool_call_id,
            name=chunks[0].tool_name,
            arguments=chunks[0].tool_arguments,
        )
        assert call.name == "list_directory"
        assert call.arguments == {"path": "/tmp"}
        assert call.id

    def test_ollama_string_arguments_normalized(self):
        """Ollama may return arguments as a JSON string."""
        event = {
            "message": {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "function": {
                            "name": "list_directory",
                            "arguments": '{"path": "/tmp"}',
                        }
                    }
                ],
            },
            "done": False,
        }
        chunks = _chunks_from_event(event)
        assert chunks[0].tool_arguments == {"path": "/tmp"}

    def test_ollama_text_event(self):
        chunks = _chunks_from_event(
            {"message": {"role": "assistant", "content": "Hello"}, "done": False}
        )
        assert len(chunks) == 1
        assert chunks[0].type == "text"
        assert chunks[0].content == "Hello"


# ---------------------------------------------------------------------------
# Streaming contract end-to-end (mocked backends)
# ---------------------------------------------------------------------------
class _FakeOllamaResponse:
    def __init__(self, lines, status_code=200):
        self.status_code = status_code
        self._lines = lines

    async def aread(self):
        return "\n".join(self._lines).encode()

    async def aiter_lines(self):
        for line in self._lines:
            yield line


class _FakeOllamaStream:
    def __init__(self, lines, status_code=200):
        self._response = _FakeOllamaResponse(lines, status_code)

    async def __aenter__(self):
        return self._response

    async def __aexit__(self, *args):
        return False


class _FakeOllamaClient:
    """Mimics httpx.AsyncClient enough for OllamaProvider.generate()."""

    lines: list[str] = []
    status_code: int = 200
    last_payload: dict | None = None

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    def stream(self, method, url, json=None):
        type(self).last_payload = json
        assert url.endswith("/api/chat")
        return _FakeOllamaStream(type(self).lines, type(self).status_code)


class _FakeHTTPX:
    AsyncClient = _FakeOllamaClient
    Timeout = httpx.Timeout
    HTTPError = httpx.HTTPError


async def test_ollama_generate_streams_text_and_tool_calls(monkeypatch):
    import app.agent.providers.ollama as ollama_mod

    monkeypatch.setattr(ollama_mod, "httpx", _FakeHTTPX)
    _FakeOllamaClient.lines = [
        '{"message": {"role": "assistant", "content": "Listing "}, "done": false}',
        '{"message": {"role": "assistant", "content": "files."}, "done": false}',
        '{"message": {"role": "assistant", "content": "", "tool_calls": '
        '[{"function": {"name": "list_directory", "arguments": {"path": "/tmp"}}}]}, '
        '"done": false}',
        '{"done": true, "done_reason": "stop"}',
    ]

    provider = OllamaProvider(model="qwen3:0.6b", base_url="http://localhost:11434")
    chunks = []
    async for chunk in provider.generate(
        messages=[LLMMessage(role="user", content="list /tmp")],
        tools=[GENERIC_TOOL],
        system="You are Odin.",
    ):
        chunks.append(chunk)

    # payload is provider-agnostic input translated to Ollama format
    payload = _FakeOllamaClient.last_payload
    assert payload["model"] == "qwen3:0.6b"
    assert payload["stream"] is True
    assert payload["messages"][0] == {"role": "system", "content": "You are Odin."}
    assert payload["tools"][0]["function"]["name"] == "list_directory"

    types_seq = [c.type for c in chunks]
    assert types_seq == ["text", "text", "tool_call", "done"]

    tool_chunk = chunks[2]
    call = LLMToolCall(
        id=tool_chunk.tool_call_id,
        name=tool_chunk.tool_name,
        arguments=tool_chunk.tool_arguments,
    )
    assert call.name == "list_directory"
    assert call.arguments == {"path": "/tmp"}


async def test_ollama_generate_reports_http_error(monkeypatch):
    import app.agent.providers.ollama as ollama_mod

    monkeypatch.setattr(ollama_mod, "httpx", _FakeHTTPX)
    _FakeOllamaClient.lines = ['{"error": "model not found"}']
    _FakeOllamaClient.status_code = 404

    provider = OllamaProvider(model="missing", base_url="http://localhost:11434")
    chunks = []
    async for chunk in provider.generate(
        messages=[LLMMessage(role="user", content="hi")],
        tools=[],
        system="",
    ):
        chunks.append(chunk)

    assert chunks[-1].type == "error"
    assert "404" in chunks[-1].error


async def test_gemini_generate_streams_text_and_tool_calls():
    captured = {}

    async def fake_stream(model, contents, config):
        captured["model"] = model
        captured["contents"] = contents
        captured["config"] = config

        async def gen():
            yield SimpleNamespace(
                candidates=[
                    SimpleNamespace(
                        content=SimpleNamespace(
                            parts=[types.Part.from_text(text="Working on it.")]
                        )
                    )
                ]
            )
            yield SimpleNamespace(
                candidates=[
                    SimpleNamespace(
                        content=SimpleNamespace(
                            parts=[
                                types.Part(
                                    function_call=types.FunctionCall(
                                        name="list_directory",
                                        args={"path": "/tmp"},
                                    ),
                                    thought_signature=b"sig-123",
                                )
                            ]
                        )
                    )
                ]
            )

        return gen()

    provider = GeminiProvider(model="gemini-2.0-flash", api_key="test-key")
    provider.client = SimpleNamespace(
        aio=SimpleNamespace(models=SimpleNamespace(generate_content_stream=fake_stream))
    )

    chunks = []
    async for chunk in provider.generate(
        messages=[LLMMessage(role="user", content="list /tmp")],
        tools=[GENERIC_TOOL],
        system="You are Odin.",
    ):
        chunks.append(chunk)

    assert [c.type for c in chunks] == ["text", "tool_call", "done"]
    assert chunks[1].tool_name == "list_directory"
    assert chunks[1].tool_arguments == {"path": "/tmp"}

    # System prompt and tools reach the Gemini config
    assert captured["model"] == "gemini-2.0-flash"
    assert captured["config"].system_instruction == "You are Odin."
    assert captured["config"].tools[0].function_declarations[0].name == "list_directory"


# ---------------------------------------------------------------------------
# Tool call history round-trip (assistant tool_calls -> tool result)
# ---------------------------------------------------------------------------
class TestToolCallHistory:
    def test_gemini_rebuilds_assistant_and_tool_messages(self):
        import base64

        signature = base64.b64encode(b"sig-123").decode("ascii")
        call = LLMToolCall(
            id="call_1",
            name="list_directory",
            arguments={"path": "/tmp"},
            metadata={"thought_signature": signature},
        )
        messages = [
            LLMMessage(role="assistant", content="", tool_calls=[call]),
            LLMMessage(
                role="tool",
                content='{"files": []}',
                tool_call_id="call_1",
                tool_name="list_directory",
            ),
        ]
        contents = _build_gemini_contents(messages)

        fc = contents[0].parts[0].function_call
        assert fc.name == "list_directory"
        assert dict(fc.args) == {"path": "/tmp"}
        # thought_signature is restored inside the Gemini adapter
        assert contents[0].parts[0].thought_signature == b"sig-123"

        fr = contents[1].parts[0].function_response
        assert fr.name == "list_directory"

    def test_ollama_rebuilds_assistant_and_tool_messages(self):
        call = LLMToolCall(
            id="call_1", name="list_directory", arguments={"path": "/tmp"}
        )
        messages = [
            LLMMessage(role="assistant", content="", tool_calls=[call]),
            LLMMessage(
                role="tool",
                content='{"files": []}',
                tool_call_id="call_1",
                tool_name="list_directory",
            ),
        ]
        out = _build_ollama_messages(messages, system="You are Odin.")

        assert out[0] == {"role": "system", "content": "You are Odin."}
        assert out[1]["role"] == "assistant"
        assert out[1]["tool_calls"] == [
            {"function": {"name": "list_directory", "arguments": {"path": "/tmp"}}}
        ]
        assert out[2]["role"] == "tool"
        assert out[2]["content"] == '{"files": []}'
        assert out[2]["tool_name"] == "list_directory"

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
        monkeypatch.setenv("ODIN_MODEL", "gemini-2.0-flash")
        monkeypatch.setenv("GEMINI_API_KEY", "abc123")
        s = Settings(_env_file=None)
        assert s.odin_model_provider == "gemini"
        assert s.odin_model == "gemini-2.0-flash"
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
        assert isinstance(provider, OllamaProvider)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------
class TestFactory:
    def test_creates_ollama_provider(self):
        s = Settings(
            odin_model_provider="ollama", odin_model="qwen3:0.6b", _env_file=None
        )
        provider = create_llm_provider(s)
        assert isinstance(provider, OllamaProvider)
        assert provider.model == "qwen3:0.6b"
        assert provider.base_url == "http://localhost:11434"

    def test_creates_gemini_provider(self):
        s = Settings(
            odin_model_provider="gemini",
            odin_model="gemini-2.0-flash",
            gemini_api_key="test-key",
            _env_file=None,
        )
        provider = create_llm_provider(s)
        assert isinstance(provider, GeminiProvider)
        assert provider.model == "gemini-2.0-flash"

    def test_provider_name_is_normalized(self):
        s = Settings(
            odin_model_provider="  OLLAMA ",
            odin_model="qwen3:0.6b",
            _env_file=None,
        )
        provider = create_llm_provider(s)
        assert isinstance(provider, OllamaProvider)

    def test_unknown_provider_raises_explicit_error(self):
        s = Settings(odin_model_provider="xyz", _env_file=None)
        with pytest.raises(ValueError) as exc:
            create_llm_provider(s)
        message = str(exc.value)
        assert "Unsupported LLM provider: xyz" in message
        assert "Supported providers: gemini, ollama" in message

    def test_gemini_without_api_key_raises(self):
        s = Settings(
            odin_model_provider="gemini",
            gemini_api_key="",
            _env_file=None,
        )
        with pytest.raises(ValueError, match="GEMINI_API_KEY"):
            create_llm_provider(s)

"""LiteLLM provider adapter tests.

Covers the unified adapter that replaced the hand-written gemini/groq/ollama
providers: message/tool conversion, streamed tool-call accumulation, verbatim
tool-call id preservation (Gemini thought signatures ride inside the id),
provider-extra round-tripping and error handling.

LiteLLM is never actually imported: a fake module stands in for it, so the
suite stays fast and network-free.
"""
import inspect
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

os.environ.setdefault("GEMINI_API_KEY", "test-key")

import app.agent.providers.litellm_provider as mod
from app.agent.providers.base import (
    LLMMessage,
    LLMProvider,
    LLMTool,
    LLMToolCall,
)
from app.agent.providers.litellm_provider import (
    LiteLLMProvider,
    _build_messages,
    _build_tools,
    _finalize_tool_calls,
    _is_retryable,
    _merge_tool_call_fragment,
    _retry_after,
    _retry_delay,
    _short_error,
)
from app.config import Settings

GENERIC_TOOL = LLMTool(
    name="list_directory",
    description="List files",
    parameters={"type": "object", "properties": {}},
)


# ---------------------------------------------------------------------------
# Fake LiteLLM streaming surface
# ---------------------------------------------------------------------------
class _FakeFunction:
    def __init__(self, name=None, arguments=None):
        self.name = name
        self.arguments = arguments


class _FakeToolCallDelta:
    def __init__(
        self, index=0, id=None, name=None, arguments=None, provider_specific_fields=None
    ):
        self.index = index
        self.id = id
        self.type = "function"
        self.function = _FakeFunction(name, arguments)
        self.provider_specific_fields = provider_specific_fields


class _FakeDelta:
    def __init__(self, content=None, tool_calls=None, provider_specific_fields=None):
        self.content = content
        self.tool_calls = tool_calls
        self.provider_specific_fields = provider_specific_fields


class _FakeChoice:
    def __init__(self, delta):
        self.delta = delta
        self.finish_reason = None


class _FakeChunk:
    def __init__(self, delta=None, usage=None):
        self.choices = [_FakeChoice(delta)] if delta is not None else []
        self.usage = usage


class _FakeLitellm:
    """Minimal stand-in for the ``litellm`` module."""

    def __init__(self, chunks, exc=None):
        self._chunks = chunks
        self._exc = exc
        self.captured: dict | None = None

    async def acompletion(self, **kwargs):
        self.captured = kwargs
        if self._exc is not None:
            raise self._exc

        async def _gen():
            for chunk in self._chunks:
                yield chunk

        return _gen()


@pytest.fixture
def use_fake_litellm(monkeypatch):
    """Install a fake litellm module and return a setter for its chunks."""

    def _install(chunks, exc=None):
        fake = _FakeLitellm(chunks, exc=exc)
        # _get_litellm() returns the cached module when set, so no real import.
        monkeypatch.setattr(mod, "_loaded_litellm", fake)
        return fake

    return _install


# ---------------------------------------------------------------------------
# Contract
# ---------------------------------------------------------------------------
class TestContract:
    def test_implements_protocol(self):
        provider = LiteLLMProvider(model="m", provider="openai", api_key="k")
        assert isinstance(provider, LLMProvider)

    def test_generate_signature_matches(self):
        sig = inspect.signature(LiteLLMProvider.generate)
        assert list(sig.parameters) == ["self", "messages", "tools", "system"]
        assert inspect.isasyncgenfunction(LiteLLMProvider.generate)


# ---------------------------------------------------------------------------
# Message / tool conversion
# ---------------------------------------------------------------------------
class TestConversion:
    def test_build_tools(self):
        assert _build_tools([GENERIC_TOOL]) == [
            {
                "type": "function",
                "function": {
                    "name": "list_directory",
                    "description": "List files",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ]

    def test_build_messages_round_trip_and_extras(self):
        call = LLMToolCall(
            id="call_1__thought__SIG",
            name="list_directory",
            arguments={"path": "/tmp"},
            metadata={"provider_specific_fields": {"thought_signature": "SIG"}},
        )
        messages = [
            LLMMessage(role="user", content="hi"),
            LLMMessage(role="assistant", content="", tool_calls=[call]),
            LLMMessage(
                role="tool",
                content='{"files": []}',
                tool_call_id="call_1__thought__SIG",
                tool_name="list_directory",
            ),
        ]
        out = _build_messages(messages, system="be brief")

        assert out[0] == {"role": "system", "content": "be brief"}
        assert out[1] == {"role": "user", "content": "hi"}

        assistant = out[2]
        assert assistant["role"] == "assistant"
        # Empty text is dropped when tool calls are present.
        assert assistant["content"] is None
        tc = assistant["tool_calls"][0]
        assert tc["id"] == "call_1__thought__SIG"  # preserved verbatim
        assert tc["type"] == "function"
        assert tc["function"] == {
            "name": "list_directory",
            "arguments": '{"path": "/tmp"}',
        }
        assert tc["provider_specific_fields"] == {"thought_signature": "SIG"}

        assert out[3] == {
            "role": "tool",
            "tool_call_id": "call_1__thought__SIG",
            "content": '{"files": []}',
        }

    def test_build_messages_keeps_text_without_tools(self):
        out = _build_messages(
            [LLMMessage(role="assistant", content="hello")], system=""
        )
        assert out == [{"role": "assistant", "content": "hello"}]


# ---------------------------------------------------------------------------
# Streamed tool-call accumulation
# ---------------------------------------------------------------------------
class TestToolCallAccumulation:
    def test_merges_argument_fragments(self):
        states: dict[int, dict] = {}
        _merge_tool_call_fragment(
            states, _FakeToolCallDelta(index=0, id="call_1", name="t", arguments='{"a":')
        )
        _merge_tool_call_fragment(
            states, _FakeToolCallDelta(index=0, arguments="1}")
        )
        chunks = _finalize_tool_calls(states)
        assert len(chunks) == 1
        assert chunks[0].tool_call_id == "call_1"
        assert chunks[0].tool_name == "t"
        assert chunks[0].tool_arguments == {"a": 1}
        assert chunks[0].metadata is None

    def test_preserves_id_and_provider_fields(self):
        states: dict[int, dict] = {}
        _merge_tool_call_fragment(
            states,
            _FakeToolCallDelta(
                index=0,
                id="call_1__thought__SIG",
                name="list_directory",
                arguments="{}",
                provider_specific_fields={"thought_signature": "SIG"},
            ),
        )
        chunks = _finalize_tool_calls(states)
        assert chunks[0].tool_call_id == "call_1__thought__SIG"
        assert chunks[0].metadata == {
            "provider_specific_fields": {"thought_signature": "SIG"}
        }

    def test_indexes_keep_order(self):
        states: dict[int, dict] = {}
        _merge_tool_call_fragment(
            states, _FakeToolCallDelta(index=1, id="b", name="second", arguments="{}")
        )
        _merge_tool_call_fragment(
            states, _FakeToolCallDelta(index=0, id="a", name="first", arguments="{}")
        )
        chunks = _finalize_tool_calls(states)
        assert [c.tool_name for c in chunks] == ["first", "second"]


# ---------------------------------------------------------------------------
# from_settings
# ---------------------------------------------------------------------------
class TestFromSettings:
    def test_builds_litellm_model_and_credentials(self):
        s = Settings(
            odin_model_provider="groq",
            odin_model="openai/gpt-oss-120b",
            groq_api_key="k",
            groq_base_url="https://api.groq.com/openai/v1",
            _env_file=None,
        )
        provider = LiteLLMProvider.from_settings(s)
        assert provider.litellm_model == "groq/openai/gpt-oss-120b"
        assert provider.api_key == "k"
        assert provider.api_base == "https://api.groq.com/openai/v1"

    def test_ollama_has_no_api_key(self):
        s = Settings(
            odin_model_provider="ollama",
            odin_model="qwen3:0.6b",
            ollama_base_url="http://localhost:11434",
            _env_file=None,
        )
        provider = LiteLLMProvider.from_settings(s)
        assert provider.api_key is None
        assert provider.api_base == "http://localhost:11434"
        assert provider.litellm_model == "ollama/qwen3:0.6b"

    def test_missing_api_key_raises(self):
        s = Settings(
            odin_model_provider="openai",
            odin_model="gpt-4o-mini",
            openai_api_key="",
            _env_file=None,
        )
        with pytest.raises(ValueError, match="OPENAI_API_KEY"):
            LiteLLMProvider.from_settings(s)


# ---------------------------------------------------------------------------
# generate() end-to-end (fake backend)
# ---------------------------------------------------------------------------
class TestGenerate:
    async def test_streams_text_and_tool_call(self, use_fake_litellm):
        fake = use_fake_litellm(
            [
                _FakeChunk(delta=_FakeDelta(content="Working ")),
                _FakeChunk(delta=_FakeDelta(content="on it.")),
                _FakeChunk(
                    delta=_FakeDelta(
                        tool_calls=[
                            _FakeToolCallDelta(
                                index=0,
                                id="call_1__thought__SIG",
                                name="list_directory",
                                arguments='{"path": "/tmp"}',
                                provider_specific_fields={"thought_signature": "SIG"},
                            )
                        ]
                    )
                ),
                _FakeChunk(usage={"total_tokens": 3}),  # usage-only chunk
            ]
        )

        provider = LiteLLMProvider(
            model="gemini-2.0-flash", provider="gemini", api_key="k"
        )
        out = []
        async for chunk in provider.generate(
            messages=[LLMMessage(role="user", content="list /tmp")],
            tools=[GENERIC_TOOL],
            system="You are Odin.",
        ):
            out.append(chunk)

        assert [c.type for c in out] == ["text", "text", "tool_call", "done"]
        tc = out[2]
        assert tc.tool_call_id == "call_1__thought__SIG"
        assert tc.tool_name == "list_directory"
        assert tc.tool_arguments == {"path": "/tmp"}
        assert tc.metadata == {"provider_specific_fields": {"thought_signature": "SIG"}}

        # The request was translated into LiteLLM's shape.
        cap = fake.captured
        assert cap["model"] == "gemini/gemini-2.0-flash"
        assert cap["stream"] is True
        assert cap["api_key"] == "k"
        assert cap["messages"][0] == {"role": "system", "content": "You are Odin."}
        assert cap["tools"][0]["function"]["name"] == "list_directory"

    async def test_reports_error(self, use_fake_litellm):
        use_fake_litellm([], exc=RuntimeError("boom"))
        provider = LiteLLMProvider(model="m", provider="ollama")
        out = []
        async for chunk in provider.generate(
            messages=[LLMMessage(role="user", content="hi")], tools=[], system=""
        ):
            out.append(chunk)
        assert out[-1].type == "error"
        assert "boom" in out[-1].error

    async def test_no_tools_omits_tools_param(self, use_fake_litellm):
        fake = use_fake_litellm([_FakeChunk(delta=_FakeDelta(content="ok"))])
        provider = LiteLLMProvider(model="m", provider="ollama")
        async for _ in provider.generate(
            messages=[LLMMessage(role="user", content="hi")], tools=[], system=""
        ):
            pass
        assert "tools" not in fake.captured


# ---------------------------------------------------------------------------
# Transient-failure detection
# ---------------------------------------------------------------------------
class _RateLimitError(Exception):
    """Duck-typed stand-in for a provider 429."""

    def __init__(self, message="rate limit exceeded", status_code=429, retry_after=None):
        super().__init__(message)
        self.status_code = status_code
        if retry_after is not None:
            self.response = SimpleNamespace(headers={"retry-after": str(retry_after)})


class TestRetryDetection:
    def test_status_code_429_is_retryable(self):
        assert _is_retryable(_RateLimitError())

    def test_5xx_message_is_retryable(self):
        assert _is_retryable(Exception("503 Service Unavailable"))

    def test_connection_error_name_is_retryable(self):
        class APIConnectionError(Exception):
            pass

        assert _is_retryable(APIConnectionError("socket closed"))

    def test_client_error_is_not_retryable(self):
        assert not _is_retryable(ValueError("invalid api key"))

    def test_retry_after_is_parsed(self):
        assert _retry_after(_RateLimitError(retry_after=7)) == 7.0
        assert _retry_after(_RateLimitError()) is None

    def test_retry_delay_honours_retry_after(self):
        assert _retry_delay(_RateLimitError(retry_after=5), 2, 1.0, 30.0) == 5.0

    def test_retry_delay_is_capped(self):
        assert _retry_delay(_RateLimitError(retry_after=600), 1, 1.0, 30.0) == 30.0

    def test_short_error_labels_rate_limit(self):
        assert _short_error(_RateLimitError()) == "rate limited"


# ---------------------------------------------------------------------------
# generate() retry behaviour
# ---------------------------------------------------------------------------
class _FlakyLitellm:
    """acompletion raises queued errors before finally streaming chunks."""

    def __init__(self, chunks, errors=()):
        self._chunks = chunks
        self._errors = list(errors)
        self.calls = 0

    async def acompletion(self, **kwargs):
        self.calls += 1
        if self._errors:
            raise self._errors.pop(0)

        async def _gen():
            for chunk in self._chunks:
                yield chunk

        return _gen()


class _StreamThenFail:
    """Streams one chunk, then raises (models a mid-stream failure)."""

    def __init__(self, chunk, exc):
        self._chunk = chunk
        self._exc = exc

    async def acompletion(self, **kwargs):
        async def _gen():
            yield self._chunk
            raise self._exc

        return _gen()


def _retry_provider(**kwargs):
    return LiteLLMProvider(
        model="m",
        provider="groq",
        max_retries=3,
        retry_base_delay=0.0,
        retry_max_delay=0.0,
        **kwargs,
    )


async def _collect(provider):
    return [
        chunk
        async for chunk in provider.generate(
            messages=[LLMMessage(role="user", content="hi")],
            tools=[],
            system="",
        )
    ]


class TestRetryBehaviour:
    async def test_retries_rate_limit_then_succeeds(self, monkeypatch):
        fake = _FlakyLitellm(
            [_FakeChunk(delta=_FakeDelta(content="hello"))], [_RateLimitError()]
        )
        monkeypatch.setattr(mod, "_loaded_litellm", fake)

        out = await _collect(_retry_provider())

        assert [c.type for c in out] == ["retry", "text", "done"]
        assert out[0].retry_after is not None
        assert "rate limited" in out[0].content
        assert fake.calls == 2

    async def test_gives_up_after_max_retries(self, monkeypatch):
        fake = _FlakyLitellm([], [_RateLimitError(), _RateLimitError()])
        monkeypatch.setattr(mod, "_loaded_litellm", fake)
        provider = LiteLLMProvider(
            model="m",
            provider="groq",
            max_retries=1,
            retry_base_delay=0.0,
            retry_max_delay=0.0,
        )

        out = await _collect(provider)

        assert [c.type for c in out] == ["retry", "error"]
        assert fake.calls == 2  # first attempt + one retry

    async def test_does_not_retry_client_errors(self, monkeypatch):
        fake = _FlakyLitellm([], [ValueError("invalid api key")])
        monkeypatch.setattr(mod, "_loaded_litellm", fake)

        out = await _collect(_retry_provider())

        assert [c.type for c in out] == ["error"]
        assert fake.calls == 1

    async def test_does_not_retry_after_text_streamed(self, monkeypatch):
        fake = _StreamThenFail(
            _FakeChunk(delta=_FakeDelta(content="partial")), _RateLimitError()
        )
        monkeypatch.setattr(mod, "_loaded_litellm", fake)

        out = await _collect(_retry_provider())

        assert [c.type for c in out] == ["text", "error"]

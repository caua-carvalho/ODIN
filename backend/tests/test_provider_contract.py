"""Provider contract suite for every provider in the catalog.

Purpose (issue #18)
-------------------
`test_litellm_provider.py` exercises the adapter against a *fake* LiteLLM;
`smoke_*.py` hit a real provider but only by hand. This module adds a
**parameterized contract suite** that:

* runs **offline by default** — no credentials, no network — over every provider
  in ``app.agent.providers.catalog.PROVIDERS`` (gemini, ollama, groq, openai,
  anthropic), reusing the fake LiteLLM backend from ``test_litellm_provider``;
* covers the behaviours that broke in the past: streaming text, streamed
  tool-call accumulation, verbatim tool-call **id** preservation + the
  ``provider_specific_fields`` round-trip (Gemini's thought signature rides in
  the id), transient-failure retry, non-retryable client errors and the
  provider-specific ``OllamaThink`` parameter (issue #16);
* exposes an **opt-in real** path (``@pytest.mark.provider_real``) that talks to
  an actual provider only when it is explicitly enabled.

Running the real, opt-in path
-----------------------------
Enable the suite with ``ODIN_CONTRACT_TESTS`` and provide the provider's
credential/base URL (everything is read from the process environment, exactly
like the app):

* all providers except Ollama need their API key: ``GEMINI_API_KEY``,
  ``GROQ_API_KEY``, ``OPENAI_API_KEY``, ``ANTHROPIC_API_KEY``. Ollama needs an
  explicit ``OLLAMA_BASE_URL`` and a running server (no key).
* ``ODIN_CONTRACT_TESTS=1`` (or ``all``/``true``) enables every provider whose
  credential is present; a comma-separated list (``ODIN_CONTRACT_TESTS=gemini,groq``)
  enables only those.

Examples::

    # Offline contract suite (the default; what CI runs)
    cd backend && .venv/bin/pytest tests/ -q

    # Only the opt-in, real provider tests — nothing runs without opt-in
    ODIN_CONTRACT_TESTS=gemini GEMINI_API_KEY=... \
        .venv/bin/pytest tests/test_provider_contract.py -m provider_real -v

    # A local Ollama server (pull qwen3:0.6b first)
    ODIN_CONTRACT_TESTS=ollama OLLAMA_BASE_URL=http://localhost:11434 \
        .venv/bin/pytest tests/test_provider_contract.py -m provider_real -v

The real calls could not be executed while writing this suite (no credentials
in the development environment); the offline path is what the default test run
guarantees. ``smoke_gemini.py`` / ``smoke_ollama.py`` are kept as quick manual
shortcuts — this suite is the reproducible, per-provider replacement.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Make sure we can import app modules (matches the other test modules).
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.agent.providers import catalog
from app.agent.providers.base import LLMMessage, LLMTool, LLMToolCall
from app.agent.providers.litellm_provider import (
    PROVIDER_FIELDS_KEY,
    LiteLLMProvider,
    _build_messages,
)
from app.config import Settings

# Reuse the fake LiteLLM surface from the adapter tests instead of duplicating
# it (the fakes are the single source of truth for the streamed chunk shapes).
from tests.test_litellm_provider import (  # noqa: E402
    _FakeChunk,
    _FakeDelta,
    _FakeLitellm,
    _FakeToolCallDelta,
    _FlakyLitellm,
    _RateLimitError,
)

import app.agent.providers.litellm_provider as mod  # noqa: E402

# Every provider the catalog supports. The offline contract tests are
# parameterized over this so a new provider is covered automatically.
PROVIDERS = tuple(sorted(catalog.PROVIDERS))

TOOL = LLMTool(
    name="list_directory",
    description="List files in a directory",
    parameters={
        "type": "object",
        "properties": {"path": {"type": "string"}},
        "required": ["path"],
    },
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _offline_provider(name: str, **overrides) -> LiteLLMProvider:
    """A provider wired to the fake backend (no credentials required)."""
    kwargs = dict(model=catalog.PROVIDERS[name].default_model, provider=name)
    kwargs.update(overrides)
    return LiteLLMProvider(**kwargs)


async def _collect(provider, *, tools=None, messages=None, system=""):
    if messages is None:
        messages = [LLMMessage(role="user", content="hi")]
    if tools is None:
        tools = []
    return [c async for c in provider.generate(messages=messages, tools=tools, system=system)]


def _install(monkeypatch, fake):
    monkeypatch.setattr(mod, "_loaded_litellm", fake)
    return fake


# ---------------------------------------------------------------------------
# Real-provider opt-in gate (issue #18)
# ---------------------------------------------------------------------------
_TRUE = {"1", "true", "yes", "all", "on"}


def _enabled_providers(env: dict[str, str]) -> set[str]:
    """Providers the user opted into via ``ODIN_CONTRACT_TESTS``.

    Empty/absent (or a falsy value) means the real path is disabled — the
    default for dev and CI.
    """
    raw = env.get("ODIN_CONTRACT_TESTS", "").strip().lower()
    if not raw or raw in {"0", "false", "no", "off"}:
        return set()
    if raw in _TRUE:
        return set(PROVIDERS)
    return {name.strip() for name in raw.split(",") if name.strip()}


def _real_configured(name: str, env: dict[str, str]) -> bool:
    """Whether the provider has the credential/base it needs to be called."""
    meta = catalog.PROVIDERS[name]
    if meta.api_key_setting:
        return bool(env.get(meta.api_key_setting.upper(), ""))
    # Ollama needs no key; require an explicit base URL so an accidental opt-in
    # never reaches a default localhost server the developer did not intend.
    return bool(env.get("OLLAMA_BASE_URL", ""))


def _skip_unless_real(name: str, env: dict[str, str]) -> None:
    if name not in _enabled_providers(env):
        pytest.skip(
            f"real {name} contract tests are opt-in: set ODIN_CONTRACT_TESTS={name} "
            "(or 1/all)"
        )
    if not _real_configured(name, env):
        setting = catalog.PROVIDERS[name].api_key_setting
        needed = setting.upper() if setting else "OLLAMA_BASE_URL"
        pytest.skip(f"real {name} contract tests need {needed} in the environment")


def _real_settings(name: str, env: dict[str, str]) -> Settings:
    """Settings for a real run.

    Credentials are passed explicitly from the pre-test snapshot instead of
    being read from ``os.environ`` (which test modules pollute with fake keys).
    """
    meta = catalog.PROVIDERS[name]
    kwargs: dict[str, object] = {
        "odin_model_provider": name,
        "odin_model": meta.default_model,
        "_env_file": None,
    }
    if meta.api_key_setting:
        kwargs[meta.api_key_setting] = env.get(meta.api_key_setting.upper(), "")
    else:
        kwargs["ollama_base_url"] = env.get("OLLAMA_BASE_URL", "")
    return Settings(**kwargs)


# ---------------------------------------------------------------------------
# Offline contract (runs by default, no network)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("name", PROVIDERS)
def test_litellm_model_uses_catalog_prefix(name):
    provider = _offline_provider(name)
    assert provider.litellm_model == f"{catalog.PROVIDERS[name].litellm_prefix}/{provider.model}"


@pytest.mark.parametrize("name", PROVIDERS)
async def test_streams_text(name, monkeypatch):
    fake = _install(
        monkeypatch,
        _FakeLitellm(
            [
                _FakeChunk(delta=_FakeDelta(content="Hel")),
                _FakeChunk(delta=_FakeDelta(content="lo")),
                _FakeChunk(usage={"total_tokens": 2}),  # usage-only chunk
            ]
        ),
    )
    provider = _offline_provider(name)

    out = await _collect(provider)

    assert [c.type for c in out] == ["text", "text", "done"]
    assert "".join(c.content or "" for c in out if c.type == "text") == "Hello"
    assert fake.captured["model"] == provider.litellm_model
    assert fake.captured["stream"] is True


@pytest.mark.parametrize("name", PROVIDERS)
async def test_accumulates_streamed_tool_call(name, monkeypatch):
    _install(
        monkeypatch,
        _FakeLitellm(
            [
                _FakeChunk(
                    delta=_FakeDelta(
                        tool_calls=[
                            _FakeToolCallDelta(
                                index=0,
                                id="call_1__thought__SIG",
                                name="list_directory",
                                arguments='{"path": "',
                            )
                        ]
                    )
                ),
                _FakeChunk(
                    delta=_FakeDelta(
                        tool_calls=[_FakeToolCallDelta(index=0, arguments='/tmp"}')]
                    )
                ),
                # Provider extras (e.g. Gemini thought signature) arrive last.
                _FakeChunk(
                    delta=_FakeDelta(
                        tool_calls=[
                            _FakeToolCallDelta(
                                index=0,
                                provider_specific_fields={"thought_signature": "SIG"},
                            )
                        ]
                    )
                ),
            ]
        ),
    )
    provider = _offline_provider(name)

    out = await _collect(provider, tools=[TOOL])

    calls = [c for c in out if c.type == "tool_call"]
    assert len(calls) == 1
    call = calls[0]
    # The id is preserved verbatim (it carries the Gemini thought signature).
    assert call.tool_call_id == "call_1__thought__SIG"
    assert call.tool_name == "list_directory"
    assert call.tool_arguments == {"path": "/tmp"}
    assert call.metadata == {PROVIDER_FIELDS_KEY: {"thought_signature": "SIG"}}


@pytest.mark.parametrize("name", PROVIDERS)
def test_provider_extras_round_trip(name):
    """A tool call reloaded from history keeps id + provider extras."""
    call = LLMToolCall(
        id="call_1__thought__SIG",
        name="list_directory",
        arguments={"path": "/tmp"},
        metadata={PROVIDER_FIELDS_KEY: {"thought_signature": "SIG"}},
    )
    out = _build_messages(
        [
            LLMMessage(role="user", content="list /tmp"),
            LLMMessage(role="assistant", content="", tool_calls=[call]),
        ],
        system="be brief",
    )
    assistant = out[-1]
    assert assistant["content"] is None  # empty text dropped alongside tools
    tc = assistant["tool_calls"][0]
    assert tc["id"] == "call_1__thought__SIG"
    assert tc["provider_specific_fields"] == {"thought_signature": "SIG"}


@pytest.mark.parametrize("name", PROVIDERS)
async def test_retries_transient_failure(name, monkeypatch):
    fake = _install(
        monkeypatch,
        _FlakyLitellm([_FakeChunk(delta=_FakeDelta(content="hi"))], [_RateLimitError()]),
    )
    provider = _offline_provider(
        name, max_retries=2, retry_base_delay=0.0, retry_max_delay=0.0
    )

    out = await _collect(provider)

    assert [c.type for c in out] == ["retry", "text", "done"]
    assert "rate limited" in out[0].content
    assert fake.calls == 2


@pytest.mark.parametrize("name", PROVIDERS)
async def test_client_error_is_not_retried(name, monkeypatch):
    fake = _install(monkeypatch, _FlakyLitellm([], [ValueError("400 invalid api key")]))
    provider = _offline_provider(
        name, max_retries=3, retry_base_delay=0.0, retry_max_delay=0.0
    )

    out = await _collect(provider)

    assert [c.type for c in out] == ["error"]
    assert "invalid api key" in out[0].error
    assert fake.calls == 1


@pytest.mark.parametrize("name", PROVIDERS)
async def test_ollama_think_is_provider_specific(name, monkeypatch):
    """The Ollama ``think`` flag reaches Ollama and only Ollama (#16)."""
    fake = _install(monkeypatch, _FakeLitellm([_FakeChunk(delta=_FakeDelta(content="hi"))]))
    provider = _offline_provider(name, ollama_think=True)

    await _collect(provider)

    if name == "ollama":
        assert fake.captured["think"] is True
    else:
        assert "think" not in fake.captured


# ---------------------------------------------------------------------------
# Real, opt-in integration (skipped by default)
# ---------------------------------------------------------------------------
@pytest.mark.provider_real
@pytest.mark.parametrize("name", PROVIDERS)
async def test_real_streams_text(name, real_provider_env):
    _skip_unless_real(name, real_provider_env)
    provider = LiteLLMProvider.from_settings(_real_settings(name, real_provider_env))

    out = await _collect(
        provider,
        messages=[LLMMessage(role="user", content="Reply with the single word: pong")],
    )

    errors = [c.error for c in out if c.type == "error"]
    assert not errors, errors
    assert "".join(c.content or "" for c in out if c.type == "text").strip()


@pytest.mark.provider_real
@pytest.mark.parametrize("name", PROVIDERS)
async def test_real_tool_call(name, real_provider_env):
    _skip_unless_real(name, real_provider_env)
    provider = LiteLLMProvider.from_settings(_real_settings(name, real_provider_env))

    out = await _collect(
        provider,
        tools=[TOOL],
        messages=[
            LLMMessage(
                role="user",
                content=(
                    "Call the list_directory tool with path=/tmp. "
                    "Invoke the tool instead of answering directly."
                ),
            )
        ],
        system="You are a concise assistant. Always use tools when asked.",
    )

    errors = [c.error for c in out if c.type == "error"]
    assert not errors, errors
    assert [c for c in out if c.type == "tool_call"], "expected a real tool call"

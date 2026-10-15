"""Unified LLM provider backed by LiteLLM.

A single adapter replaces the three hand-written ones (``gemini.py``,
``groq.py``, ``ollama.py``). LiteLLM speaks the OpenAI chat-completions shape
for every supported vendor, so one streaming + tool-call normalization works
everywhere. Vendor selection is by prefix (see ``catalog.PROVIDERS``):

    gemini/gemini-2.5-flash
    groq/llama-3.3-70b-versatile
    ollama/qwen3:0.6b
    openai/gpt-4o-mini
    anthropic/claude-3-5-sonnet-latest

Provider-specific extras that must survive a round-trip (notably Gemini thought
signatures) are carried opaquely in ``LLMToolCall.metadata`` under
``provider_specific_fields`` and re-emitted unchanged. The tool-call ``id`` is
also preserved verbatim: LiteLLM encodes the Gemini thought signature inside
that id (separator ``__thought__``) and reconstructs it on the next request, so
keeping the id intact is what makes multi-turn Gemini tool calling work — never
regenerate it for a LiteLLM provider.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any, AsyncIterator

from app.agent.providers.base import LLMChunk, LLMMessage, LLMTool, LLMToolCall

logger = logging.getLogger("odin.agent.providers.litellm")

# Key under which LiteLLM places provider-specific extras on a tool call
# (e.g. ``{"thought_signature": "..."}`` for Gemini).
PROVIDER_FIELDS_KEY = "provider_specific_fields"

# Settings attribute holding the API base override for providers that need one.
_API_BASE_SETTING = {
    "ollama": "ollama_base_url",
    "groq": "groq_base_url",
}

# LiteLLM is loaded lazily (see ``_get_litellm``): importing it costs ~15s, so
# it must never run at module import / app startup.
_loaded_litellm: Any | None = None


def _get_litellm() -> Any:
    """Return the LiteLLM module, importing it on first use."""
    global _loaded_litellm
    if _loaded_litellm is None:
        import litellm  # noqa: PLC0415 — intentionally lazy (heavy import)

        # Never fail a request just because a model rejects an optional param,
        # and keep LiteLLM's own banner out of the app logs.
        litellm.drop_params = True
        litellm.suppress_debug_info = True
        _loaded_litellm = litellm
    return _loaded_litellm


def warm() -> None:
    """Pre-load LiteLLM so the first request does not pay the import cost.

    Intended to be called from a background thread during app startup.
    Best-effort: a failure here must never break startup.
    """
    try:
        _get_litellm()
    except Exception as exc:  # pragma: no cover - warm-up is best effort
        logger.warning(f"Could not pre-load LiteLLM: {exc}")


def _get(obj: Any, key: str, default: Any = None) -> Any:
    """Read ``key`` from a mapping or an object attribute (both shapes occur)."""
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


# ---------------------------------------------------------------------------
# Internal -> LiteLLM (OpenAI chat) format
# ---------------------------------------------------------------------------
def _build_messages(messages: list[LLMMessage], system: str) -> list[dict]:
    """Convert internal messages to the OpenAI chat format LiteLLM expects."""
    out: list[dict] = []

    if system:
        out.append({"role": "system", "content": system})

    for msg in messages:
        if msg.role == "system":
            continue  # system handled above

        if msg.role == "user":
            out.append({"role": "user", "content": msg.content})

        elif msg.role == "assistant":
            content: str | None = msg.content or ""
            if msg.tool_calls and not content:
                # Providers reject an empty text part alongside tool calls.
                content = None
            entry: dict = {"role": "assistant", "content": content}
            if msg.tool_calls:
                entry["tool_calls"] = [
                    _tool_call_to_dict(tc) for tc in msg.tool_calls
                ]
            out.append(entry)

        elif msg.role == "tool":
            out.append(
                {
                    "role": "tool",
                    "tool_call_id": msg.tool_call_id or "",
                    "content": msg.content,
                }
            )

    return out


def _tool_call_to_dict(tc: LLMToolCall) -> dict:
    """Rebuild one assistant tool call, preserving LiteLLM provider extras."""
    entry: dict = {
        "id": tc.id,
        "type": "function",
        "function": {
            "name": tc.name,
            "arguments": json.dumps(tc.arguments or {}),
        },
    }
    extras = (tc.metadata or {}).get(PROVIDER_FIELDS_KEY)
    if extras:
        entry[PROVIDER_FIELDS_KEY] = extras
    return entry


def _build_tools(tools: list[LLMTool]) -> list[dict]:
    """Convert generic tool definitions to the OpenAI tool format."""
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


# ---------------------------------------------------------------------------
# LiteLLM (OpenAI chat) stream -> internal tool calls
# ---------------------------------------------------------------------------
def _merge_tool_call_fragment(
    states: dict[int, dict], tc_delta: Any, delta: Any = None
) -> None:
    """Accumulate one streamed tool-call delta into ``states[index]``.

    Arguments arrive in fragments; the id/name come on the first fragment. The
    id is kept verbatim (it may embed a Gemini thought signature).
    """
    index = _get(tc_delta, "index")
    if index is None:
        index = 0
    state = states.setdefault(
        index, {"id": None, "name": "", "arguments": "", PROVIDER_FIELDS_KEY: None}
    )

    tc_id = _get(tc_delta, "id")
    if tc_id:
        state["id"] = tc_id

    function = _get(tc_delta, "function")
    if function is not None:
        name = _get(function, "name")
        if name:
            state["name"] = name
        fragment = _get(function, "arguments")
        if fragment:
            state["arguments"] += fragment

    extras = _get(tc_delta, PROVIDER_FIELDS_KEY)
    if not extras and delta is not None:
        extras = _get(delta, PROVIDER_FIELDS_KEY)
    if extras:
        state[PROVIDER_FIELDS_KEY] = extras


def _finalize_tool_calls(states: dict[int, dict]) -> list[LLMChunk]:
    """Flatten accumulated tool-call deltas into complete chunks."""
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

        extras = state.get(PROVIDER_FIELDS_KEY)
        chunks.append(
            LLMChunk(
                type="tool_call",
                tool_call_id=state.get("id") or str(uuid.uuid4()),
                tool_name=state.get("name") or "",
                tool_arguments=arguments,
                metadata={PROVIDER_FIELDS_KEY: extras} if extras else None,
            )
        )
    return chunks


class LiteLLMProvider:
    """LLM provider that delegates to LiteLLM for every vendor."""

    def __init__(
        self,
        model: str,
        provider: str = "",
        api_key: str | None = None,
        api_base: str | None = None,
        litellm_model: str | None = None,
    ) -> None:
        self.provider = (provider or "").strip().lower()
        self.model = model
        self.api_key = api_key or None
        self.api_base = api_base or None
        self.litellm_model = litellm_model or (
            f"{self.provider}/{model}" if self.provider else model
        )
        logger.info(f"LiteLLMProvider initialized: {self.litellm_model}")

    @classmethod
    def from_settings(cls, config: Any, provider: str | None = None) -> "LiteLLMProvider":
        """Build a provider from ``Settings`` (or a settings-like object).

        Raises ``ValueError`` with a ``<PROVIDER>_API_KEY not configured``
        message when the selected provider needs a key that is missing.
        """
        # Imported here to avoid a circular import with the factory.
        from app.agent.providers import catalog

        name = (provider or config.odin_model_provider or "").strip().lower()
        meta = catalog.PROVIDERS.get(name)
        prefix = getattr(meta, "litellm_prefix", None) or name

        model = config.odin_model
        litellm_model = (
            model if model.startswith(f"{prefix}/") else f"{prefix}/{model}"
        )

        api_key = None
        if meta is not None and meta.api_key_setting:
            api_key = getattr(config, meta.api_key_setting, "") or ""
            if not api_key:
                raise ValueError(f"{meta.api_key_setting.upper()} not configured")

        base_setting = _API_BASE_SETTING.get(name)
        api_base = getattr(config, base_setting, "") if base_setting else None

        return cls(
            model=model,
            provider=name,
            api_key=api_key,
            api_base=api_base,
            litellm_model=litellm_model,
        )

    async def generate(
        self,
        messages: list[LLMMessage],
        tools: list[LLMTool],
        system: str,
    ) -> AsyncIterator[LLMChunk]:
        """Stream a response from LiteLLM, yielding normalized chunks."""
        litellm = _get_litellm()

        kwargs: dict[str, Any] = {
            "model": self.litellm_model,
            "messages": _build_messages(messages, system),
            "stream": True,
            "temperature": 0.7,
        }
        built_tools = _build_tools(tools)
        if built_tools:
            kwargs["tools"] = built_tools
        if self.api_key:
            kwargs["api_key"] = self.api_key
        if self.api_base:
            kwargs["api_base"] = self.api_base

        tool_states: dict[int, dict] = {}

        try:
            response = await litellm.acompletion(**kwargs)

            async for chunk in response:
                choices = _get(chunk, "choices") or []
                if not choices:
                    # Usage-only or empty keep-alive chunk.
                    usage = _get(chunk, "usage")
                    if usage:
                        logger.debug(f"LLM usage: {usage}")
                    continue

                delta = _get(choices[0], "delta")
                if delta is None:
                    continue

                content = _get(delta, "content")
                if content:
                    yield LLMChunk(type="text", content=content)

                for tc_delta in _get(delta, "tool_calls") or []:
                    _merge_tool_call_fragment(tool_states, tc_delta, delta)

            for tool_chunk in _finalize_tool_calls(tool_states):
                yield tool_chunk

            yield LLMChunk(type="done")

        except Exception as exc:
            logger.error(f"LiteLLM generation error: {exc}", exc_info=True)
            yield LLMChunk(type="error", error=str(exc))
